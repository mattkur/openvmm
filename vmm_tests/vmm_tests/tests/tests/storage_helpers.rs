// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

//! Common routines and helpers for storage-related tests.

use petri::PetriVm;
use petri::PetriVmmBackend;

pub(crate) struct ExpectedNvmeDeviceProperties {
    pub save_restore_supported: bool,
    pub qsize: u64,
    pub nvme_keepalive: bool,
}

/// Check that the NVMe driver state in the VM matches the expected properties.
/// If `props` is `None`, then we skip validating the properties.
pub(crate) async fn check_expected_nvme_driver_state<T: PetriVmmBackend>(
    vm: &PetriVm<T>,
    props: &Option<ExpectedNvmeDeviceProperties>,
) -> Result<(), anyhow::Error> {
    let devices = vm.inspect_openhcl("vm/nvme/devices", None, None).await?;
    tracing::info!(devices = %devices.json(), "NVMe devices");

    let devices: serde_json::Value = serde_json::from_str(&format!("{}", devices.json()))?;

    /*
    {
        "718b:00:00.0": {
            "driver": {
                "driver": {
                    "admin": {
                        ...
                    },
                    "bounce_buffer": false,
                    "device": {
                        "dma_client": {
                            "backing": {
                                "type": "locked_memory"
                            },
                            "params": {
                                "allocation_visibility": "private",
                                "device_name": "nvme_718b:00:00.0",
                                "lower_vtl_policy": "any",
                                "persistent_allocations": false
                            }
                        },
                        "interrupts": {
                            "0": {
                                "target_cpu": 0
                            }
                        },
                        "pci_id": "718b:00:00.0"
                    },
                    "device_id": "718b:00:00.0",
                    "identify": {
                        ...
                    },
                    "io": {
                        ...
                    },
                    "io_issuers": {
                        ...
                    },
                    "max_io_queues": 1,
                    "nvme_keepalive": false,
                    "qsize": 64,
                    "registers": {
                        ...
                    }
                },
                "pci_id": "718b:00:00.0"
            },
            "pci_id": "718b:00:00.0",
            "save_restore_supported": false,
            "vp_count": 1
        }
    }
    */

    // If just one device is returned, then this will be a `Value::Object`, where the
    // key is the single PCI ID of the device.
    //
    // TODO (future PR): Fix this up with support for multiple devices when this code is used
    // in more complicated tests.
    let found_device_id = devices
        .as_object()
        .expect("devices object")
        .keys()
        .next()
        .expect("device id");

    // The PCI id is generated from the VMBUS instance guid for vpci devices.
    // See `PARAVISOR_BOOT_NVME_INSTANCE`.
    assert_eq!(found_device_id, "718b:00:00.0");
    if let Some(props) = props {
        assert_eq!(
            devices[found_device_id]["driver"]["driver"]["qsize"]
                .as_u64()
                .expect("qsize"),
            props.qsize
        );
        assert_eq!(
            devices[found_device_id]["driver"]["driver"]["nvme_keepalive"]
                .as_bool()
                .expect("nvme_keepalive"),
            props.nvme_keepalive
        );
        assert_eq!(
            devices[found_device_id]["save_restore_supported"]
                .as_bool()
                .expect("save_restore_supported"),
            props.save_restore_supported
        );
    }

    Ok(())
}
