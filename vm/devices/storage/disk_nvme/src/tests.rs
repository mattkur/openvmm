// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

use chipset_device::mmio::ExternallyManagedMmioIntercepts;
use chipset_device::mmio::MmioIntercept;
use chipset_device::pci::PciConfigSpace;
use disk_backend::DiskIo;
use disk_backend::pr;
use guid::Guid;
use inspect::Inspect;
use inspect::InspectMut;
use mesh::CellUpdater;
use nvme::NvmeControllerCaps;
use nvme_driver::NvmeDriver;
use nvme_resources::fault::AdminQueueFaultConfig;
use nvme_resources::fault::FaultConfiguration;
use nvme_resources::fault::QueueFaultBehavior;
use nvme_spec::AdminOpcode;
use nvme_spec::Cap;
use nvme_spec::Command;
use nvme_spec::nvm::DsmRange;
use nvme_test::command_match::CommandMatchBuilder;
use pal_async::DefaultDriver;
use pal_async::async_test;
use parking_lot::Mutex;
use pci_core::msi::MsiInterruptSet;
use scsi_buffers::OwnedRequestBuffers;
use std::sync::Arc;
use std::sync::atomic::AtomicBool;
use std::sync::atomic::Ordering;
use test_with_tracing::test;
use user_driver::DeviceBacking;
use user_driver::DeviceRegisterIo;
use user_driver::DmaClient;
use user_driver::interrupt::DeviceInterrupt;
use user_driver_emulated_mock::DeviceTestDmaClientCallbacks;
use user_driver_emulated_mock::DeviceTestMemory;
use user_driver_emulated_mock::EmulatedDevice;
use user_driver_emulated_mock::Mapping;
use vmcore::vm_task::SingleDriverBackend;
use vmcore::vm_task::VmTaskDriverSource;
use zerocopy::FromZeros;
use zerocopy::IntoBytes;

#[async_test]
async fn test_too_many_registrants(driver: DefaultDriver) {
    // The first 8bytes of the response buffer correspond to the nsze field of the Identify Namespace data structure.
    // Reduce the reported size of the namespace to 256 blocks instead of the original 512.
    let mut buf: u64 = 256;
    let buf = buf.as_mut_bytes();
    let mut fault_start_updater = CellUpdater::new(true);
    let fault_configuration = FaultConfiguration::new(fault_start_updater.cell())
        .with_admin_queue_fault(
            AdminQueueFaultConfig::new().with_completion_queue_fault(
                CommandMatchBuilder::new()
                    .match_cdw0_opcode(nvme_spec::AdminOpcode::IDENTIFY.0)
                    .match_cdw10(
                        nvme_spec::Cdw10Identify::new()
                            .with_cns(nvme_spec::Cns::NAMESPACE.0)
                            .into(),
                        nvme_spec::Cdw10Identify::new().with_cns(u8::MAX).into(),
                    )
                    .build(),
                QueueFaultBehavior::CustomPayload(buf.to_vec()),
            ),
        );

    const MSIX_COUNT: u16 = 2;
    const IO_QUEUE_COUNT: u16 = 64;
    const CPU_COUNT: u32 = 64;

    // Arrange: Create 8MB of space. First 4MB for the device and second 4MB for the payload.
    let pages = 1024; // 4MB
    let device_test_memory = DeviceTestMemory::new(pages * 2, false, "test_nvme_driver");
    let guest_mem = device_test_memory.guest_memory(); // Access to 0-8MB
    let dma_client = device_test_memory.dma_client(); // Access 0-4MB
    let payload_mem = device_test_memory.payload_mem(); // allow_dma is false, so this will follow the 'normal' test path (i.e. with bounce buffering behind the scenes)

    // Arrange: Create the NVMe controller and driver.
    let driver_source = VmTaskDriverSource::new(SingleDriverBackend::new(driver));
    let mut msi_set = MsiInterruptSet::new();
    let nvme = nvme_test::NvmeFaultController::new(
        &driver_source,
        guest_mem.clone(),
        &mut msi_set,
        &mut ExternallyManagedMmioIntercepts,
        nvme_test::NvmeFaultControllerCaps {
            msix_count: MSIX_COUNT,
            max_io_queues: IO_QUEUE_COUNT,
            subsystem_id: Guid::new_random(),
        },
        fault_configuration,
    );

    nvme.client() // 2MB namespace
        .add_namespace(1, disklayer_ram::ram_disk(2 << 20, false).unwrap())
        .await
        .unwrap();
    let device = NvmeTestEmulatedDevice::new(nvme, msi_set, dma_client.clone());
    let driver = NvmeDriver::new(&driver_source, CPU_COUNT, device, false)
        .await
        .unwrap();
    let namespace = driver.namespace(1).await.unwrap();

    let disk = crate::NvmeDisk::new(namespace);

    let foo = disk.report().await;

    // // Act: Write 1024 bytes of data to disk starting at LBA 1.
    // let buf_range = OwnedRequestBuffers::linear(0, 16384, true); // 32 blocks
    // payload_mem.write_at(0, &[0xcc; 4096]).unwrap();
    // namespace
    //     .write(
    //         0,
    //         1,
    //         2,
    //         false,
    //         &payload_mem,
    //         buf_range.buffer(&payload_mem).range(),
    //     )
    //     .await
    //     .unwrap();

    driver.shutdown().await;
}

#[derive(Inspect)]
pub struct NvmeTestEmulatedDevice<T: InspectMut, U: DmaClient> {
    device: EmulatedDevice<T, U>,
    #[inspect(debug)]
    mocked_response_u32: Arc<Mutex<Option<(usize, u32)>>>,
    #[inspect(debug)]
    mocked_response_u64: Arc<Mutex<Option<(usize, u64)>>>,
}

#[derive(Inspect)]
pub struct NvmeTestMapping<T> {
    mapping: Mapping<T>,
    #[inspect(debug)]
    mocked_response_u32: Arc<Mutex<Option<(usize, u32)>>>,
    #[inspect(debug)]
    mocked_response_u64: Arc<Mutex<Option<(usize, u64)>>>,
}

impl<T: PciConfigSpace + MmioIntercept + InspectMut, U: DmaClient> NvmeTestEmulatedDevice<T, U> {
    /// Creates a new emulated device, wrapping `device`, using the provided MSI controller.
    pub fn new(device: T, msi_set: MsiInterruptSet, dma_client: Arc<U>) -> Self {
        Self {
            device: EmulatedDevice::new(device, msi_set, dma_client.clone()),
            mocked_response_u32: Arc::new(Mutex::new(None)),
            mocked_response_u64: Arc::new(Mutex::new(None)),
        }
    }

    // TODO: set_mock_response_u32 is intentionally not implemented to avoid dead code.
    pub fn set_mock_response_u64(&mut self, mapping: Option<(usize, u64)>) {
        let mut mock_response = self.mocked_response_u64.lock();
        *mock_response = mapping;
    }
}

/// Implementation of DeviceBacking trait for NvmeTestEmulatedDevice
impl<T: 'static + Send + InspectMut + MmioIntercept, U: 'static + DmaClient> DeviceBacking
    for NvmeTestEmulatedDevice<T, U>
{
    type Registers = NvmeTestMapping<T>;

    fn id(&self) -> &str {
        self.device.id()
    }

    fn map_bar(&mut self, n: u8) -> anyhow::Result<Self::Registers> {
        Ok(NvmeTestMapping {
            mapping: self.device.map_bar(n).unwrap(),
            mocked_response_u32: Arc::clone(&self.mocked_response_u32),
            mocked_response_u64: Arc::clone(&self.mocked_response_u64),
        })
    }

    fn dma_client(&self) -> Arc<dyn DmaClient> {
        self.device.dma_client()
    }

    fn max_interrupt_count(&self) -> u32 {
        self.device.max_interrupt_count()
    }

    fn map_interrupt(&mut self, msix: u32, _cpu: u32) -> anyhow::Result<DeviceInterrupt> {
        self.device.map_interrupt(msix, _cpu)
    }
}

impl<T: MmioIntercept + Send> DeviceRegisterIo for NvmeTestMapping<T> {
    fn len(&self) -> usize {
        self.mapping.len()
    }

    fn read_u32(&self, offset: usize) -> u32 {
        let mock_response = self.mocked_response_u32.lock();

        // Intercept reads to the mocked offset address
        if let Some((mock_offset, mock_data)) = *mock_response {
            if mock_offset == offset {
                return mock_data;
            }
        }

        self.mapping.read_u32(offset)
    }

    fn read_u64(&self, offset: usize) -> u64 {
        let mock_response = self.mocked_response_u64.lock();

        // Intercept reads to the mocked offset address
        if let Some((mock_offset, mock_data)) = *mock_response {
            if mock_offset == offset {
                return mock_data;
            }
        }

        self.mapping.read_u64(offset)
    }

    fn write_u32(&self, offset: usize, data: u32) {
        self.mapping.write_u32(offset, data);
    }

    fn write_u64(&self, offset: usize, data: u64) {
        self.mapping.write_u64(offset, data);
    }
}
