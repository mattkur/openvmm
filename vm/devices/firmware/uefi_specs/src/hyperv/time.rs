// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

//! Hyper-V specific UEFI Time definitions

use crate::uefi::common::EfiStatus64;
use crate::uefi::time::EFI_TIME;
use zerocopy::IntoBytes;
use zerocopy::KnownLayout;

use zerocopy::Immutable;
use zerocopy::FromBytes;


/// MsvmPkg: `VM_EFI_TIME``
#[repr(C, packed)]
#[derive(Debug, Clone, Copy, IntoBytes, Immutable, FromBytes)]
pub struct VmEfiTime {
    pub status: EfiStatus64,
    pub time: EFI_TIME,
}
