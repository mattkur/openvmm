// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

//! A shim layer to fuzz responses from an emulated device.
use std::collections::HashMap;
use std::iter::Map;

use crate::arbitrary_data;

use chipset_device::mmio::MmioIntercept;
use chipset_device::pci::PciConfigSpace;
use inspect::Inspect;
use inspect::InspectMut;
use pci_core::msi::MsiInterruptSet;
use user_driver::emulated::DeviceSharedMemory;
use user_driver::emulated::EmulatedDevice;
use user_driver::emulated::EmulatedDmaAllocator;
use user_driver::emulated::Mapping;
use user_driver::interrupt::DeviceInterrupt;
use user_driver::DeviceBacking;
use user_driver::DeviceRegisterIo;

/// An EmulatedDevice fuzzer that requires a working EmulatedDevice backend.
#[derive(Inspect)]
pub struct FuzzEmulatedDevice<T: PciConfigSpace + MmioIntercept + InspectMut> {
    device: EmulatedDevice<T>,
    #[inspect(skip)]
    bars: HashMap<u8, <FuzzEmulatedDevice<T> as DeviceBacking>::Registers>,
}

pub struct FuzzMapping<T> {
    device_bar: Mapping<T>,
}

impl<T: PciConfigSpace + MmioIntercept + InspectMut> FuzzEmulatedDevice<T> {
    /// Creates a new emulated device, wrapping `device`, using the provided MSI controller.
    pub fn new(device: T, msi_set: MsiInterruptSet, shared_mem: DeviceSharedMemory) -> Self {
        Self {
            device: EmulatedDevice::new(device, msi_set, shared_mem),
            bars: HashMap::new(),
        }
    }
}

impl<T: PciConfigSpace + MmioIntercept + InspectMut> DeviceRegisterIo for FuzzMapping<T> {
    fn read_u32(&self, offset: usize) -> u32 {
        if let Ok(true) = arbitrary_data::<bool>() {
            if let Ok(data) = arbitrary_data::<u32>() {
                return data;
            }
        }

        self.device_bar.read_u32(offset)
    }

    fn read_u64(&self, offset: usize) -> u64 {
        if let Ok(true) = arbitrary_data::<bool>() {
            if let Ok(data) = arbitrary_data::<u64>() {
                return data;
            }
        }

        self.device_bar.read_u64(offset)
    }

    fn write_u32(&self, offset: usize, data: u32) {
        self.device_bar.write_u32(offset, data)
    }

    fn write_u64(&self, offset: usize, data: u64) {
        self.device_bar.write_u64(offset, data)
    }
}

/// Implementation for DeviceBacking trait.
impl<T: 'static + Send + InspectMut + MmioIntercept> DeviceBacking for FuzzEmulatedDevice<T> {
    type Registers = Mapping<T>;
    type DmaAllocator = EmulatedDmaAllocator;

    fn id(&self) -> &str {
        self.device.id()
    }

    fn map_bar(&mut self, n: u8) -> anyhow::Result<Self::Registers> {
        let device_bar = self.device.map_bar(n)?;

        let fuzz_mapping = FuzzMapping { device_bar };
        self.bars.insert(n, fuzz_mapping);

        Ok(fuzz_mapping)
    }

    fn host_allocator(&self) -> Self::DmaAllocator {
        self.device.host_allocator()
    }


    /// Arbitrarily decide to passthrough or return arbitrary value.
    fn max_interrupt_count(&self) -> u32 {
        // Case: Fuzz response
        if let Ok(true) = arbitrary_data::<bool>() {
            // Return an abritrary u32
            if let Ok(num) = arbitrary_data::<u32>() {
                return num;
            }
        }

        // Case: Passthrough
        self.device.max_interrupt_count()
    }

    fn map_interrupt(&mut self, msix: u32, _cpu: u32) -> anyhow::Result<DeviceInterrupt> {
        self.device.map_interrupt(msix, _cpu)
    }
}
