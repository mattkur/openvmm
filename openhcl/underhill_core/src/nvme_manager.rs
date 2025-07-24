// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

//! Provides access to NVMe namespaces that are backed by the user-mode NVMe
//! VFIO driver. Keeps track of all the NVMe drivers.

use crate::nvme_manager::namespace::NvmeDriverManager;
use crate::nvme_manager::save_restore::NvmeManagerSavedState;
use crate::nvme_manager::save_restore::NvmeSavedDiskConfig;
use crate::servicing::NvmeSavedState;
use anyhow::Context;
use async_trait::async_trait;
use disk_backend::resolve::ResolveDiskParameters;
use disk_backend::resolve::ResolvedDisk;
use futures::StreamExt;
use futures::TryFutureExt;
use futures::future::join_all;
use inspect::Inspect;
use mesh::MeshPayload;
use mesh::rpc::Rpc;
use mesh::rpc::RpcError;
use mesh::rpc::RpcSend;
use openhcl_dma_manager::AllocationVisibility;
use openhcl_dma_manager::DmaClientParameters;
use openhcl_dma_manager::DmaClientSpawner;
use openhcl_dma_manager::LowerVtlPermissionPolicy;
use pal_async::task::Spawn;
use pal_async::task::Task;
use std::collections::HashMap;
use std::collections::hash_map;
use std::sync::Arc;
use thiserror::Error;
use tracing::Instrument;
use user_driver::vfio::PciDeviceResetMethod;
use user_driver::vfio::VfioDevice;
use user_driver::vfio::vfio_set_device_reset_method;
use vm_resource::AsyncResolveResource;
use vm_resource::ResourceId;
use vm_resource::ResourceResolver;
use vm_resource::kind::DiskHandleKind;
use vmcore::vm_task::VmTaskDriverSource;

#[derive(Debug, Error)]
#[error("nvme device {pci_id} error")]
pub struct NamespaceError {
    pci_id: String,
    #[source]
    source: InnerError,
}

#[derive(Debug, Error)]
enum InnerError {
    #[error("failed to initialize vfio device")]
    Vfio(#[source] anyhow::Error),
    #[error("failed to initialize nvme device")]
    DeviceInitFailed(#[source] anyhow::Error),
    #[error("failed to create dma client for device")]
    DmaClient(#[source] anyhow::Error),
    #[error("failed to get namespace {nsid}")]
    Namespace {
        nsid: u32,
        #[source]
        source: nvme_driver::NamespaceError,
    },
    #[error("device manager is already shutdown")]
    DeviceManagerShutdown(#[from] RpcError), // todo: not quite right, since this will swallow an RpcError::Call.
}

mod namespace {
    use super::*;
    use nvme_driver::NvmeDriverSavedState;

    #[derive(Debug, Clone)]
    pub struct NvmeDriverShutdownOptions {
        /// If true, the device will not reset on shutdown.
        pub do_not_reset: bool,

        /// If true, skip the underlying nvme device shutdown path when tearing
        /// down the driver. Used for NVMe keepalive.
        pub skip_device_shutdown: bool,
    }

    enum NvmeDriverRequest {
        /// Get an instance of the supplied namespace (an nvme `nsid`).
        GetNamespace(Rpc<u32, Result<nvme_driver::Namespace, InnerError>>),
        Save(Rpc<(), Result<NvmeDriverSavedState, anyhow::Error>>),
        /// Shutdown the NVMe driver, and the manager of that driver. Takes a single `bool`: whether this device should reset
        Shutdown(Rpc<NvmeDriverShutdownOptions, ()>),
    }

    #[derive(Inspect)]
    /// Owns a single instance of an nvme driver.
    pub struct NvmeDriverManager {
        #[inspect(skip)]
        task: Task<()>,
        pci_id: String,
        pub client: NvmeDriverManagerClient,
    }

    impl NvmeDriverManager {
        pub fn client(&self) -> &NvmeDriverManagerClient {
            &self.client
        }

        /// Creates the [`NvmeController`].
        pub async fn new(
            driver_source: &VmTaskDriverSource,
            pci_id: &str,
            vp_count: u32,
            nvme_always_flr: bool,
            is_isolated: bool,
            save_restore_supported: bool,
            dma_client_spawner: DmaClientSpawner,
        ) -> Result<Self, InnerError> {
            // todo: dedicate a vp for each instance of this
            // todo: deal with inspect
            let (send, recv) = mesh::channel();
            let driver = driver_source.simple();

            let dma_client = dma_client_spawner
                .new_client(DmaClientParameters {
                    device_name: format!("nvme_{}", pci_id),
                    lower_vtl_policy: LowerVtlPermissionPolicy::Any,
                    allocation_visibility: if is_isolated {
                        AllocationVisibility::Shared
                    } else {
                        AllocationVisibility::Private
                    },
                    persistent_allocations: save_restore_supported,
                })
                .map_err(InnerError::DmaClient)?;

            let mut worker = NvmeDriverManagerWorker {
                driver_source: driver_source.clone(),
                pci_id: pci_id.into(),
                vp_count,
                driver: Some(
                    create_nvme_device(
                        driver_source,
                        pci_id,
                        vp_count,
                        nvme_always_flr,
                        is_isolated,
                        dma_client,
                    )
                    .await?,
                ),
            };
            let task = driver.spawn("nvme-driver-manager", async move { worker.run(recv).await });
            Ok(Self {
                task,
                pci_id: pci_id.into(),
                client: NvmeDriverManagerClient {
                    pci_id: pci_id.into(),
                    sender: send,
                },
            })
        }

        /// Creates the [`NvmeController`].
        pub fn new_restored(
            driver_source: &VmTaskDriverSource,
            pci_id: &str,
            vp_count: u32,
            device: nvme_driver::NvmeDriver<VfioDevice>,
        ) -> Result<Self, InnerError> {
            // todo: dedicate a vp for each instance of this
            // todo: deal with save/restore
            // todo: deal with inspect
            let (send, recv) = mesh::channel();
            let driver = driver_source.simple();

            let mut worker = NvmeDriverManagerWorker {
                driver_source: driver_source.clone(),
                pci_id: pci_id.into(),
                vp_count,
                driver: Some(device),
            };
            let task = driver.spawn("nvme-driver-manager", async move { worker.run(recv).await });
            Ok(Self {
                task,
                pci_id: pci_id.into(),
                client: NvmeDriverManagerClient {
                    pci_id: pci_id.into(),
                    sender: send,
                },
            })
        }

        pub async fn shutdown(self, opts: NvmeDriverShutdownOptions) {
            // Early return is faster way to skip shutdown.
            // but we need to thoroughly test the data integrity.
            // TODO: Enable this once tested and approved.
            //
            // if self.nvme_keepalive { return }

            // todo: gracefully handle case where shutdown is already called
            // (but that code path cannot happen by construction, today)
            self.client()
                .sender
                .call(NvmeDriverRequest::Shutdown, opts.clone())
                .instrument(tracing::info_span!(
                    "nvme_driver_manager_shutdown",
                    pci_id = self.pci_id,
                    do_not_reset = opts.do_not_reset,
                    skip_device_shutdown = opts.skip_device_shutdown
                ))
                .await
                .expect("nvme driver manager is shut down"); // <-- when driver manager is already shutdown

            self.task.await;
        }

        /// Save NVMe manager's state during servicing.
        pub async fn save(&self) -> Result<NvmeDriverSavedState, anyhow::Error> {
            // NVMe manager has no own data to save, everything will be done
            // in the Worker task which can be contacted through Client.
            self.client
                .save()
                .instrument(tracing::info_span!("nvme_driver_manager_save", %self.pci_id))
                .await
        }
    }

    #[derive(Inspect, Debug, Clone)]
    pub struct NvmeDriverManagerClient {
        pci_id: String,
        #[inspect(skip)]
        sender: mesh::Sender<NvmeDriverRequest>,
    }

    impl NvmeDriverManagerClient {
        pub async fn get_namespace(&self, nsid: u32) -> Result<nvme_driver::Namespace, InnerError> {
            Ok(self
                .sender
                .call(NvmeDriverRequest::GetNamespace, nsid)
                .instrument(tracing::info_span!(
                    "nvme_driver_client_get_namespace",
                    pci_id = self.pci_id,
                    nsid
                ))
                .await?  // <-- when driver manager is already shutdown
                ?)
        }

        pub(in crate::nvme_manager::namespace) async fn save(
            &self,
        ) -> Result<NvmeDriverSavedState, anyhow::Error> {
            // todo: gracefully handle case where shutdown is already called
            // (but that code path cannot happen by construction, today)
            Ok(self
                .sender
                .call(NvmeDriverRequest::Save, ())
                .instrument(tracing::info_span!(
                    "nvme_driver_client_save",
                    pci_id = self.pci_id
                ))
                .await
                .context("nvme driver manager worker is shut down")? // <-- when driver manager is already shutdown
                ?)
        }
    }

    #[derive(Inspect)]
    struct NvmeDriverManagerWorker {
        #[inspect(skip)]
        driver_source: VmTaskDriverSource,
        pci_id: String,
        vp_count: u32,
        driver: Option<nvme_driver::NvmeDriver<VfioDevice>>,
    }

    impl NvmeDriverManagerWorker {
        async fn run(&mut self, mut recv: mesh::Receiver<NvmeDriverRequest>) {
            loop {
                let Some(req) = recv.next().await else {
                    break;
                };
                // While it is conceivable that there could be multiple, concurrent `GetNamespace` calls
                // for the same device, this code chooses to serialize them. This is implicit in that this
                // is one task, and it does not loop until the `GetNamespace` call finishes.
                //
                // The dominant time is in setting up the _device_, which cannot be done concurrently.
                // Setting up a namespace should be relatively fast, only limited by the time taken
                // to issue an `IDENTIFY NVME NAMESPACE` command.
                match req {
                    NvmeDriverRequest::GetNamespace(rpc) => {
                        tracing::trace!(
                            "nvme driver manager worker get namespace {nsid} {pci_id}",
                            pci_id = self.pci_id,
                            nsid = rpc.input().clone()
                        );
                        rpc.handle(async |nsid| {
                            self.driver
                                .as_ref()
                                .unwrap() // todo
                                .namespace(nsid)
                                .await
                                .map_err(|source| InnerError::Namespace { nsid, source })
                        })
                        .await
                    }
                    NvmeDriverRequest::Save(rpc) => {
                        tracing::trace!("nvme driver manager save {pci_id}", pci_id = self.pci_id);
                        rpc.handle(async |()| self.driver.as_mut().unwrap().save().await)
                            .await
                    }
                    NvmeDriverRequest::Shutdown(rpc) => {
                        tracing::trace!(
                            "nvme driver manager shutdown {pci_id}",
                            pci_id = self.pci_id
                        );
                        rpc.handle(async |options| {
                            let mut me = self
                                .driver
                                .take()
                                .expect("nvme driver manager shutdown called without driver");

                            me.update_servicing_flags(options.do_not_reset);

                            if !options.skip_device_shutdown {
                                // todo: make sure that `drop` happens at the right time (e.g. why did the code call `shutdown`
                                // at all if we are skipping the reset). And, do_not_reset is the same as skip_shutdown at the caller
                                me.shutdown()
                                    .instrument(
                                        tracing::info_span!("shutdown_nvme_controller", %self.pci_id),
                                    )
                                    .await;
                            }
                        })
                        .await;

                        break;
                    }
                }
            }
        }
    }
}

#[derive(Debug)]
pub struct NvmeManager {
    task: Task<()>,
    client: NvmeManagerClient,
    /// Running environment (memory layout) supports save/restore.
    save_restore_supported: bool,
}

impl Inspect for NvmeManager {
    fn inspect(&self, req: inspect::Request<'_>) {
        let mut resp = req.respond();
        // Pull out the field that force loads a driver on a device and handle
        // it separately.
        resp.child("force_load_pci_id", |req| match req.update() {
            Ok(update) => {
                self.client
                    .sender
                    .send(Request::ForceLoadDriver(update.defer()));
            }
            Err(req) => req.value(""),
        });
        // Send the remaining fields directly to the worker.
        resp.merge(inspect::adhoc(|req| {
            self.client.sender.send(Request::Inspect(req.defer()))
        }));
    }
}

impl NvmeManager {
    pub fn new(
        driver_source: &VmTaskDriverSource,
        vp_count: u32,
        save_restore_supported: bool,
        nvme_always_flr: bool,
        is_isolated: bool,
        saved_state: Option<NvmeSavedState>,
        dma_client_spawner: DmaClientSpawner,
    ) -> Self {
        let (send, recv) = mesh::channel();
        let driver = driver_source.simple();
        let mut worker = NvmeManagerWorker {
            driver_source: driver_source.clone(),
            devices: HashMap::new(),
            vp_count,
            save_restore_supported,
            nvme_always_flr,
            is_isolated,
            dma_client_spawner,
        };
        let task = driver.spawn("nvme-manager", async move {
            // Restore saved data (if present) before async worker thread runs.
            if let Some(s) = saved_state.as_ref() {
                if let Err(e) = NvmeManager::restore(&mut worker, s)
                    .instrument(tracing::info_span!("nvme_manager_restore"))
                    .await
                {
                    tracing::error!(
                        error = e.as_ref() as &dyn std::error::Error,
                        "failed to restore nvme manager"
                    );
                }
            };
            worker.run(recv).await
        });
        Self {
            task,
            client: NvmeManagerClient { sender: send },
            save_restore_supported,
        }
    }

    pub fn client(&self) -> &NvmeManagerClient {
        &self.client
    }

    pub async fn shutdown(self, nvme_keepalive: bool) {
        // Early return is faster way to skip shutdown.
        // but we need to thoroughly test the data integrity.
        // TODO: Enable this once tested and approved.
        //
        // if self.nvme_keepalive { return }
        self.client.sender.send(Request::Shutdown {
            span: tracing::info_span!("shutdown_nvme_manager"),
            nvme_keepalive,
        });
        self.task.await;
    }

    /// Save NVMe manager's state during servicing.
    pub async fn save(&self, nvme_keepalive: bool) -> Option<NvmeManagerSavedState> {
        // NVMe manager has no own data to save, everything will be done
        // in the Worker task which can be contacted through Client.
        if self.save_restore_supported && nvme_keepalive {
            Some(self.client().save().await?)
        } else {
            // Do not save any state if nvme_keepalive
            // was explicitly disabled.
            None
        }
    }

    /// Restore NVMe manager's state after servicing.
    async fn restore(
        worker: &mut NvmeManagerWorker,
        saved_state: &NvmeSavedState,
    ) -> anyhow::Result<()> {
        worker
            .restore(&saved_state.nvme_state)
            .instrument(tracing::info_span!("nvme_manager_worker_restore"))
            .await?;

        Ok(())
    }
}

enum Request {
    Inspect(inspect::Deferred),
    ForceLoadDriver(inspect::DeferredUpdate),
    GetNamespace(Rpc<(String, u32), Result<nvme_driver::Namespace, NamespaceError>>),
    Save(Rpc<(), Result<NvmeManagerSavedState, anyhow::Error>>),
    Shutdown {
        span: tracing::Span,
        nvme_keepalive: bool,
    },
}

#[derive(Debug, Clone)]
pub struct NvmeManagerClient {
    sender: mesh::Sender<Request>,
}

impl NvmeManagerClient {
    pub async fn get_namespace(
        &self,
        pci_id: String,
        nsid: u32,
    ) -> anyhow::Result<nvme_driver::Namespace> {
        Ok(self
            .sender
            .call(Request::GetNamespace, (pci_id.clone(), nsid))
            .instrument(tracing::info_span!(
                "nvme_manager_get_namespace",
                pci_id,
                nsid
            ))
            .await
            .context("nvme manager is shut down")??)
    }

    /// Send an RPC call to save NVMe worker data.
    pub async fn save(&self) -> Option<NvmeManagerSavedState> {
        match self.sender.call(Request::Save, ()).await {
            Ok(s) => s.ok(),
            Err(_) => None,
        }
    }
}

#[derive(Inspect)]
struct NvmeManagerWorker {
    #[inspect(skip)]
    driver_source: VmTaskDriverSource,
    #[inspect(iter_by_key)]
    devices: HashMap<String, Option<NvmeDriverManager>>,
    vp_count: u32,
    /// Running environment (memory layout) allows save/restore.
    save_restore_supported: bool,
    nvme_always_flr: bool,
    /// If this VM is isolated or not. This influences DMA client allocations.
    is_isolated: bool,
    #[inspect(skip)]
    dma_client_spawner: DmaClientSpawner,
}

async fn create_nvme_device(
    driver_source: &VmTaskDriverSource,
    pci_id: &str,
    vp_count: u32,
    nvme_always_flr: bool,
    is_isolated: bool,
    dma_client: Arc<dyn user_driver::DmaClient>,
) -> Result<nvme_driver::NvmeDriver<VfioDevice>, InnerError> {
    // Disable FLR on vfio attach/detach; this allows faster system
    // startup/shutdown with the caveat that the device needs to be properly
    // sent through the shutdown path during servicing operations, as that is
    // the only cleanup performed. If the device fails to initialize, turn FLR
    // on and try again, so that the reset is invoked on the next attach.
    let update_reset = |method: PciDeviceResetMethod| {
        if let Err(err) = vfio_set_device_reset_method(pci_id, method) {
            tracing::warn!(
                ?method,
                err = &err as &dyn std::error::Error,
                "Failed to update reset_method"
            );
        }
    };
    let mut last_err = None;
    let reset_methods = if nvme_always_flr {
        &[PciDeviceResetMethod::Flr][..]
    } else {
        // If this code can't create a device without resetting it, then still try to issue an FLR
        // in case that unwedges something weird in the device state.
        // (This is implicit when the code in [`try_create_nvme_device`] opens a handle to the
        // Vfio device).
        &[PciDeviceResetMethod::NoReset, PciDeviceResetMethod::Flr][..]
    };
    for reset_method in reset_methods {
        update_reset(*reset_method);
        match try_create_nvme_device(
            driver_source,
            pci_id,
            vp_count,
            is_isolated,
            dma_client.clone(),
        )
        .await
        {
            Ok(device) => {
                if !nvme_always_flr && !matches!(reset_method, PciDeviceResetMethod::NoReset) {
                    update_reset(PciDeviceResetMethod::NoReset);
                }
                return Ok(device);
            }
            Err(err) => {
                tracing::error!(
                    pci_id,
                    ?reset_method,
                    err = &err as &dyn std::error::Error,
                    "failed to create nvme device"
                );
                last_err = Some(err);
            }
        }
    }
    // Return the most reliable error (this code assumes that the reset methods are in increasing order
    // of reliability).
    Err(last_err.unwrap())
}

async fn try_create_nvme_device(
    driver_source: &VmTaskDriverSource,
    pci_id: &str,
    vp_count: u32,
    is_isolated: bool,
    dma_client: Arc<dyn user_driver::DmaClient>,
) -> Result<nvme_driver::NvmeDriver<VfioDevice>, InnerError> {
    let device = VfioDevice::new(driver_source, pci_id, dma_client)
        .instrument(tracing::info_span!("vfio_device_open", pci_id))
        .await
        .map_err(InnerError::Vfio)?;

    // TODO: For now, any isolation means use bounce buffering. This
    // needs to change when we have nvme devices that support DMA to
    // confidential memory.
    nvme_driver::NvmeDriver::new(driver_source, vp_count, device, is_isolated)
        .instrument(tracing::info_span!("nvme_driver_init", pci_id))
        .await
        .map_err(InnerError::DeviceInitFailed)
}

impl NvmeManagerWorker {
    async fn run(&mut self, mut recv: mesh::Receiver<Request>) {
        let (join_span, nvme_keepalive) = loop {
            let Some(req) = recv.next().await else {
                break (tracing::Span::none(), false);
            };
            match req {
                Request::Inspect(deferred) => deferred.inspect(&self),
                Request::ForceLoadDriver(update) => {
                    match self.get_driver(update.new_value().to_owned()).await {
                        Ok(_) => {
                            let pci_id = update.new_value().to_string();
                            update.succeed(pci_id);
                        }
                        Err(err) => {
                            update.fail(err);
                        }
                    }
                }
                Request::GetNamespace(rpc) => {
                    rpc.handle(async |(pci_id, nsid)| {
                        self.get_namespace(pci_id.clone(), nsid)
                            .map_err(|source| NamespaceError { pci_id, source })
                            .await
                    })
                    .await
                }
                // Request to save worker data for servicing.
                Request::Save(rpc) => {
                    rpc.handle(async |_| self.save().await)
                        .instrument(tracing::info_span!("nvme_manager_worker_save_state"))
                        .await
                }
                Request::Shutdown {
                    span,
                    nvme_keepalive,
                } => {
                    // todo: locking
                    break (span, nvme_keepalive);
                }
            }
        };

        // When nvme_keepalive flag is set then this block is unreachable
        // because the Shutdown request is never sent. // todo: <-- this was an existing comment. Is it true that we never get a Shutdown request?
        //
        // Tear down all the devices if nvme_keepalive is not set.

        // Send, and wait for completion, any shutdown requests to the individual drivers.
        // After this completes, the `NvmeDriverManager` instances will remain alive, but the
        // drivers they control will be shutdown (as appropriate).
        //
        // This is required even if `nvme_keepalive` is set, since the underlying drivers
        // need to be told to not reset.
        async {
            join_all(self.devices.iter_mut().map(|(_pci_id, driver)| {
                driver
                    .take()
                    .unwrap() // todo: handle gracefully (race against driver remove here ...)
                    .shutdown(namespace::NvmeDriverShutdownOptions {
                        // nvme_keepalive is received from host but it is only valid
                        // when memory pool allocator supports save/restore.
                        do_not_reset: nvme_keepalive && self.save_restore_supported,
                        skip_device_shutdown: nvme_keepalive && self.save_restore_supported,
                    })
                    .instrument(tracing::info_span!("shutdown_nvme_driver"))
            }))
            .await
        }
        .instrument(join_span)
        .await;
    }

    async fn get_driver(&mut self, pci_id: String) -> Result<&mut NvmeDriverManager, InnerError> {
        let driver = match self.devices.entry(pci_id.to_owned()) {
            hash_map::Entry::Occupied(entry) => entry.into_mut(),
            hash_map::Entry::Vacant(entry) => {
                let driver = NvmeDriverManager::new(
                    &self.driver_source,
                    &pci_id,
                    self.vp_count,
                    self.nvme_always_flr,
                    self.is_isolated,
                    self.save_restore_supported,
                    self.dma_client_spawner.clone(),
                )
                .instrument(
                    tracing::info_span!("create_nvme_device", %pci_id, self.nvme_always_flr),
                )
                .await?;

                entry.insert(Some(driver))
            }
        };
        Ok(driver.as_mut().unwrap())
    }

    async fn get_namespace(
        &mut self,
        pci_id: String,
        nsid: u32,
    ) -> Result<nvme_driver::Namespace, InnerError> {
        let driver = self.get_driver(pci_id.to_owned()).await?;
        driver.client().get_namespace(nsid).await
    }

    /// Saves NVMe device's states into buffer during servicing.
    pub async fn save(&mut self) -> anyhow::Result<NvmeManagerSavedState> {
        let mut nvme_disks: Vec<NvmeSavedDiskConfig> = Vec::new();
        for (pci_id, driver) in self.devices.iter_mut() {
            nvme_disks.push(NvmeSavedDiskConfig {
                pci_id: pci_id.clone(),
                driver_state: driver
                    .as_ref()
                    .unwrap()
                    .save()
                    .instrument(tracing::info_span!("nvme_driver_save", %pci_id))
                    .await?,
            });
        }

        Ok(NvmeManagerSavedState {
            cpu_count: self.vp_count,
            nvme_disks,
        })
    }

    /// Restore NVMe manager and device states from the buffer after servicing.
    pub async fn restore(&mut self, saved_state: &NvmeManagerSavedState) -> anyhow::Result<()> {
        self.devices = HashMap::new();
        for disk in &saved_state.nvme_disks {
            let pci_id = disk.pci_id.clone();

            let dma_client = self.dma_client_spawner.new_client(DmaClientParameters {
                device_name: format!("nvme_{}", pci_id),
                lower_vtl_policy: LowerVtlPermissionPolicy::Any,
                allocation_visibility: if self.is_isolated {
                    AllocationVisibility::Shared
                } else {
                    AllocationVisibility::Private
                },
                persistent_allocations: true,
            })?;

            // todo (mattkur): spawn this into separate threads, since creating the driver can block
            // will take as a future improvement.

            // This code can wait on each VFIO device until it is arrived.
            // A potential optimization would be to delay VFIO operation
            // until it is ready, but a redesign of VfioDevice is needed.
            let vfio_device =
                VfioDevice::restore(&self.driver_source, &disk.pci_id.clone(), true, dma_client)
                    .instrument(tracing::info_span!("vfio_device_restore", pci_id))
                    .await?;

            // TODO: For now, any isolation means use bounce buffering. This
            // needs to change when we have nvme devices that support DMA to
            // confidential memory.
            let nvme_driver = nvme_driver::NvmeDriver::restore(
                &self.driver_source,
                saved_state.cpu_count,
                vfio_device,
                &disk.driver_state,
                self.is_isolated,
            )
            .instrument(tracing::info_span!("nvme_driver_restore"))
            .await?;

            self.devices.insert(
                disk.pci_id.clone(),
                Some(NvmeDriverManager::new_restored(
                    &self.driver_source,
                    &pci_id,
                    self.vp_count,
                    nvme_driver,
                )?),
            );
        }
        Ok(())
    }
}

pub struct NvmeDiskResolver {
    manager: NvmeManagerClient,
}

impl NvmeDiskResolver {
    pub fn new(manager: NvmeManagerClient) -> Self {
        Self { manager }
    }
}

#[async_trait]
impl AsyncResolveResource<DiskHandleKind, NvmeDiskConfig> for NvmeDiskResolver {
    type Output = ResolvedDisk;
    type Error = anyhow::Error;

    async fn resolve(
        &self,
        _resolver: &ResourceResolver,
        rsrc: NvmeDiskConfig,
        _input: ResolveDiskParameters<'_>,
    ) -> Result<Self::Output, Self::Error> {
        let namespace = self
            .manager
            .get_namespace(rsrc.pci_id, rsrc.nsid)
            .await
            .context("could not open nvme namespace")?;

        Ok(ResolvedDisk::new(disk_nvme::NvmeDisk::new(namespace)).context("invalid disk")?)
    }
}

#[derive(MeshPayload, Default)]
pub struct NvmeDiskConfig {
    pub pci_id: String,
    pub nsid: u32,
}

impl ResourceId<DiskHandleKind> for NvmeDiskConfig {
    const ID: &'static str = "nvme";
}

pub mod save_restore {
    use mesh::payload::Protobuf;
    use vmcore::save_restore::SavedStateRoot;

    #[derive(Protobuf, SavedStateRoot)]
    #[mesh(package = "underhill")]
    pub struct NvmeManagerSavedState {
        #[mesh(1)]
        pub cpu_count: u32,
        #[mesh(2)]
        pub nvme_disks: Vec<NvmeSavedDiskConfig>,
    }

    #[derive(Protobuf, Clone)]
    #[mesh(package = "underhill")]
    pub struct NvmeSavedDiskConfig {
        #[mesh(1)]
        pub pci_id: String,
        #[mesh(2)]
        pub driver_state: nvme_driver::NvmeDriverSavedState,
    }
}
