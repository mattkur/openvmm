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
use xtask_fuzz::fuzz_eprintln;
use zerocopy::AsBytes;

// // Anything consumed by EmulatedDeviceFuzzer needs to be static because of DeviceBacking trait.
// pub static RAW_DATA: Mutex<Vec<u8>> = Mutex::new(Vec::new());

// /// Returns an arbitrary data of type T or a NotEnoughData error. Generic type must
// /// implement Arbitrary (for any lifetime 'a) and the Sized traits.
// pub fn arbitrary_data<T>() -> Result<T, arbitrary::Error>
// where
//     for<'a> T: Arbitrary<'a> + Sized,
// {
//     let mut raw_data = RAW_DATA.lock();
//     let input = raw_data.split_off(0); // Take all raw_data
//     let mut u = Unstructured::new(&input);

//     if u.is_empty() {
//         return Err(arbitrary::Error::NotEnoughData);
//     }

//     // If bytes needed is more than remaining bytes it will pad with 0s.
//     let arbitrary_type: T = u.arbitrary()?;

//     let x = u.take_rest().to_vec();
//     *raw_data = x;
//     Ok(arbitrary_type)
// }

#[derive(Arbitrary, Debug)]
struct StaticFuzzConfig {
    foo: u32,
}

fn do_fuzz(u: &mut Unstructured<'_>) -> Result<(), anyhow::Error> {
    fuzz_eprintln!("repro-ing test case...");

    DefaultPool::run_with(|driver| async move {
        // set up the channels and worker
        //let channel_count = u.int_in_range(16..=17)?; // TODO: figure out why this needs 16K  space, it seems.
        let channel_count = 16;
        let (host, guest) = connected_async_channels(channel_count * 1024);
        let guest_queue = Queue::new(guest).unwrap();

        let guest_mem_pages = u.int_in_range(1..=64)?;
        let test_guest_mem = GuestMemory::allocate(guest_mem_pages * 4096); // TODO: [use-arbitrary-input]
        let controller = ScsiController::new();
        let disk_len_sectors = u.int_in_range(1..=40960)?;
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

        // TODO: Decide whether to do protocol nogotiation or not based on arbitrary.
        guest.perform_protocol_negotiation().await;

        while !u.is_empty() {
            if let Ok(packet) = storvsp::protocol::Packet::arbitrary(u) {
                let _ = guest.send_data_packet_sync(&[packet.as_bytes()]).await;
            }
        }

        Ok::<(), anyhow::Error>(())
    })?;

    Ok(())
}

fuzz_target!(|input: &[u8]| -> libfuzzer_sys::Corpus {
    xtask_fuzz::init_tracing_if_repro();

    // {
    //     let mut raw_data = RAW_DATA.lock();
    //     *raw_data = input;
    // }

    if do_fuzz(&mut Unstructured::new(input)).is_err() {
        libfuzzer_sys::Corpus::Reject
    } else {
        libfuzzer_sys::Corpus::Keep
    }
});
