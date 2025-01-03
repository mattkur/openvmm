// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

#![cfg_attr(all(target_os = "linux", target_env = "gnu"), no_main)]

use arbitrary::Arbitrary;
use arbitrary::Unstructured;
use guestmem::ranges::PagedRange;
use guestmem::GuestMemory;
use libfuzzer_sys::fuzz_target;
use pal_async::DefaultPool;
use std::sync::Arc;
use storvsp::protocol::Packet;
use storvsp::protocol::ScsiRequest;
use storvsp::test_helpers::TestGuest;
use storvsp::test_helpers::TestWorker;
use storvsp::{ScsiController, ScsiControllerDisk};
use vmbus_async::queue::OutgoingPacket;
use vmbus_async::queue::Queue;
use vmbus_channel::connected_async_channels;
use vmbus_ring::OutgoingPacketType;
use vmbus_ring::PAGE_SIZE;
use xtask_fuzz::fuzz_eprintln;
use zerocopy::AsBytes;

#[derive(Arbitrary)]
pub enum StovspFuzzAction {
    SendDataPacket,
    SendRawPacket,
}

#[derive(Arbitrary)]
enum FuzzOutgoingPacketType {
    InBandNoCompletion,
    InBandWithCompletion,
    Completion,
    GpaDirectPacket,
}

fn page_add(offset: u64, len: u64) -> Option<u64> {
    offset
        .checked_add(len)?
        .checked_add(PAGE_SIZE as u64)?
        .checked_sub(1)?
        .checked_div(PAGE_SIZE as u64)
}

fn do_fuzz(u: &mut Unstructured<'_>) -> Result<(), anyhow::Error> {
    fuzz_eprintln!("repro-ing test case...");

    DefaultPool::run_with(|driver| async move {
        // set up the channels and worker
        let channel_count = 16; // TODO: [use-arbitrary-input] (figure out why this needs 16K  space, it seems.)
        let (host, guest_channel) = connected_async_channels(channel_count * 1024);
        let guest_queue = Queue::new(guest_channel).unwrap();

        let guest_mem_pages = u.int_in_range(1..=256)?;
        let test_guest_mem = GuestMemory::allocate(guest_mem_pages * 4096); // TODO: [use-arbitrary-input]
        let controller = ScsiController::new();
        let disk_len_sectors = u.int_in_range(1..=1048576)?; // up to 512mb in 512 byte sectors
        let disk = scsidisk::SimpleScsiDisk::new(
            disklayer_ram::ram_disk(disk_len_sectors * 512, false).unwrap(), // TODO: [use-arbitrary-input]
            Default::default(),
        );
        controller.attach(u.arbitrary()?, ScsiControllerDisk::new(Arc::new(disk)))?;

        let _test_worker = TestWorker::start(
            controller,
            driver.clone(),
            test_guest_mem.clone(),
            host,
            None,
        );

        let mut guest = TestGuest {
            queue: guest_queue,
            transaction_id: 0,
        };

        if u.ratio(9, 10)? {
            guest.perform_protocol_negotiation().await;
        }

        while !u.is_empty() {
            let action = u.arbitrary::<StovspFuzzAction>()?;
            match action {
                StovspFuzzAction::SendDataPacket => {
                    let packet = u.arbitrary::<Packet>()?;
                    let _ = guest.send_data_packet_sync(&[packet.as_bytes()]).await;
                }
                StovspFuzzAction::SendRawPacket => {
                    let packet_type = u.arbitrary()?;
                    match packet_type {
                        FuzzOutgoingPacketType::InBandNoCompletion => {
                            let packet = OutgoingPacket {
                                transaction_id: u.arbitrary::<u64>()?,
                                packet_type: OutgoingPacketType::InBandNoCompletion,
                                payload: &[&[0u8; 0]], // TODO: [use-arbitrary-input]
                            };

                            guest.queue.split().1.write(packet).await?;
                        }
                        FuzzOutgoingPacketType::InBandWithCompletion => {
                            let packet = OutgoingPacket {
                                transaction_id: u.arbitrary::<u64>()?,
                                packet_type: OutgoingPacketType::InBandWithCompletion,
                                payload: &[&[0u8; 0]], // TODO: [use-arbitrary-input]
                            };

                            guest.queue.split().1.write(packet).await?;
                        }
                        FuzzOutgoingPacketType::Completion => {
                            let packet = OutgoingPacket {
                                transaction_id: u.arbitrary::<u64>()?,
                                packet_type: OutgoingPacketType::Completion,
                                payload: &[&[0u8; 0]], // TODO: [use-arbitrary-input]
                            };

                            guest.queue.split().1.write(packet).await?;
                        }
                        FuzzOutgoingPacketType::GpaDirectPacket => {
                            let gpa_start = u.arbitrary::<u64>()?;
                            // limit the byte length to something that will fit
                            // into the collection of gpns below.
                            let max_byte_len = u.arbitrary_len::<u64>()? * PAGE_SIZE;
                            let byte_len: usize = u.int_in_range(0..=max_byte_len)?;

                            let start_page: u64 = gpa_start / PAGE_SIZE as u64;
                            if let Some(end_page) = page_add(start_page, byte_len as u64) {
                                let gpns: Vec<u64> = (start_page..end_page).collect();
                                if let Some(pages) = PagedRange::new(
                                    gpa_start as usize % PAGE_SIZE,
                                    byte_len,
                                    gpns.as_slice(),
                                ) {
                                    let header = u.arbitrary::<Packet>()?;
                                    let scsi_req = u.arbitrary::<ScsiRequest>()?;
                                    guest
                                        .queue
                                        .split()
                                        .1
                                        .write(OutgoingPacket {
                                            packet_type: OutgoingPacketType::GpaDirect(&[pages]),
                                            transaction_id: u.arbitrary::<u64>()?,
                                            payload: &[header.as_bytes(), scsi_req.as_bytes()],
                                        })
                                        .await?
                                } else {
                                    anyhow::bail!("failed to create PagedRange");
                                }
                            } else {
                                anyhow::bail!("failed to calculate end_page");
                            }
                        }
                    }
                }
            }
        }

        Ok(())
    })?;

    Ok(())
}

fuzz_target!(|input: &[u8]| -> libfuzzer_sys::Corpus {
    xtask_fuzz::init_tracing_if_repro();

    let _ = do_fuzz(&mut Unstructured::new(input));

    // Always keep the corpus, since errors are a reasonable outcome.
    // A future optimization would be to reject any corpus entries that
    // result in the inability to generate arbitrary data from the Unstructured...
    libfuzzer_sys::Corpus::Keep
});
