// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

//! Additional functionality for `zerocopy` traits.

#![no_std]

use zerocopy::FromBytes;
use zerocopy::Immutable;
use zerocopy::Ref;
use zerocopy::Unalign;

// mattkur TODO
pub trait FromBytesExt: FromBytes + Immutable {
    /// Reads a copy of Self from the prefix of bytes. Returns both the copy of Self and the remaining unused bytes.
    fn read_from_prefix_split(bytes: &[u8]) -> Option<(Self, &[u8])>
    where
        Self: Sized,
    {
        Self::read_from_prefix(bytes).ok() // todo mattkur preserve error
                                           // Ref::<_, Unalign<Self>>::new_unaligned_from_prefix(bytes)
                                           //     .map(|(r, s)| (r.read().into_inner(), s))
    }

    /// Reads a copy of Self from the suffix of bytes. Returns both the remaining unused bytes and the copy of Self.
    fn read_from_suffix_split(bytes: &[u8]) -> Option<(&[u8], Self)>
    where
        Self: Sized,
    {
        Self::read_from_suffix(bytes).ok() // todo mattkur preserve error
                                           // Ref::<_, Unalign<Self>>::new_unaligned_from_suffix(bytes)
                                           //     .map(|(s, r)| (s, r.read().into_inner()))
    }
}

impl<T: FromBytes + Immutable> FromBytesExt for T {}
