// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

#![cfg_attr(all(target_os = "linux", target_env = "gnu"), no_main)]

use arbitrary::Arbitrary;
use arbitrary::Unstructured;
use guestmem::GuestMemory;
use libfuzzer_sys::fuzz_target;
//use pal_async::DefaultDriver;
use pal_async::DefaultPool;
use parking_lot::Mutex;
use std::sync::Arc;
use storvsp::test_helpers::TestGuest;
use storvsp::test_helpers::TestWorker;
use storvsp::{ScsiController, ScsiControllerDisk};
use storvsp_resources::ScsiPath;
use vmbus_async::queue::Queue;
use vmbus_channel::connected_async_channels;
//use vmcore::vm_task::{SingleDriverBackend, VmTaskDriverSource};
use std::sync::mpsc::channel;
use vmbus_async::queue::OutgoingPacketType;
use xtask_fuzz::fuzz_eprintln;
use zerocopy::AsBytes;

#[derive(Arbitrary, Debug)]
struct StaticFuzzConfig {
    foo: u32,
}

#[derive(Arbitrary)]
pub enum StovspFuzzAction {
    SendDataPacket,
    SendRawPacket,
}

#[derive(Arbitrary)]
enum MyOutgoingPacketType {
    InBandNoCompletion,
    InBandWithCompletion,
    Completion,
    // TODO: Support GpaDirectPacket
}

fn arbitrary_outgoing_packet<'_, '_>(
    u: &'_ mut Unstructured<'_>,
) -> Result<vmbus_async::queue::OutgoingPacket<'_, '_>, arbitrary::Error> {
    let packet_type = MyOutgoingPacketType::arbitrary(u)?;
    match packet_type {
        MyOutgoingPacketType::InBandNoCompletion => Ok(vmbus_async::queue::OutgoingPacket {
            transaction_id: u.arbitrary::<u64>()?,
            packet_type: OutgoingPacketType::InBandNoCompletion,
            payload: &[&[0u8; 0]], // TODO: [use-arbitrary-input]
        }),
        MyOutgoingPacketType::InBandWithCompletion => Ok(vmbus_async::queue::OutgoingPacket {
            transaction_id: u.arbitrary::<u64>()?,
            packet_type: OutgoingPacketType::InBandWithCompletion,
            payload: &[&[0u8; 0]], // TODO: [use-arbitrary-input]
        }),
        MyOutgoingPacketType::Completion => Ok(vmbus_async::queue::OutgoingPacket {
            transaction_id: u.arbitrary::<u64>()?,
            packet_type: OutgoingPacketType::Completion,
            payload: &[&[0u8; 0]], // TODO: [use-arbitrary-input]
        }),
    }
}

fn do_fuzz(u: &mut Unstructured<'_>) -> Result<(), anyhow::Error> {
    fuzz_eprintln!("repro-ing test case...");

    DefaultPool::run_with(|driver| async move {
        // set up the channels and worker
        let channel_count = 16; // TODO: [use-arbitrary-input] (figure out why this needs 16K  space, it seems.)
        let (host, guest) = connected_async_channels(channel_count * 1024);
        let guest_queue = Queue::new(guest).unwrap();

        let guest_mem_pages = u.int_in_range(1..=256)?;
        let test_guest_mem = GuestMemory::allocate(guest_mem_pages * 4096); // TODO: [use-arbitrary-input]
        let controller = ScsiController::new();
        let disk_len_sectors = u.int_in_range(1..=1048576)?; // up to 512mb in 512 byte sectors
        let disk = scsidisk::SimpleScsiDisk::new(
            disklayer_ram::ram_disk(disk_len_sectors * 512, false).unwrap(), // TODO: [use-arbitrary-input]
            Default::default(),
        );
        controller.attach(
            ScsiPath::arbitrary(u)?,
            ScsiControllerDisk::new(Arc::new(disk)),
        )?;

        let _test_worker = TestWorker::start(
            controller.state.clone(),
            driver.clone(),
            test_guest_mem.clone(),
            host,
            None,
        );

        let mut guest = TestGuest {
            queue: guest_queue,
            transaction_id: 0,
        };

        while !u.is_empty() {
            let action = u.arbitrary::<StovspFuzzAction>()?;
            match action {
                StovspFuzzAction::SendDataPacket => {
                    if let Ok(packet) = storvsp::protocol::Packet::arbitrary(u) {
                        let _ = guest.send_data_packet_sync(&[packet.as_bytes()]).await;
                    }
                }
                StovspFuzzAction::SendRawPacket => {
                    if let Ok(packet) = arbitrary_outgoing_packet(u) {
                        guest.queue.split().1.write(packet).await?;
                    }
                }
            }
        }

        Ok::<(), anyhow::Error>(())
    })?;

    Ok(())
}

fuzz_target!(|input: &[u8]| -> libfuzzer_sys::Corpus {
    xtask_fuzz::init_tracing_if_repro();

    if do_fuzz(&mut Unstructured::new(input)).is_err() {
        libfuzzer_sys::Corpus::Reject
    } else {
        libfuzzer_sys::Corpus::Keep
    }
});
