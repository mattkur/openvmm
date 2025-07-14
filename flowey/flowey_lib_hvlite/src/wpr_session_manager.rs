// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

//! Node for managing WPR tracing sessions during test execution.

use crate::wpr_tracing::WprSession;
use flowey::node::prelude::*;
use std::collections::BTreeMap;

flowey_request! {
    pub struct Request {
        /// Name of the test session (used for WPR session naming)
        pub session_name: String,
        /// Additional environment variables from test setup
        pub extra_env: ReadVar<BTreeMap<String, String>>,
        /// Pre-run dependencies
        pub pre_run_deps: Vec<ReadVar<SideEffect>>,
        /// WPR trace file output (if tracing was enabled and successful)
        pub trace_file: Option<WriteVar<Option<PathBuf>>>,
        /// Side effect indicating WPR session is ready
        pub wpr_ready: WriteVar<SideEffect>,
    }
}

new_flow_node!(struct Node);

impl FlowNode for Node {
    type Request = Request;

    fn imports(_ctx: &mut ImportCtx<'_>) {}

    fn emit(requests: Vec<Self::Request>, ctx: &mut NodeCtx<'_>) -> anyhow::Result<()> {
        for Request {
            session_name,
            extra_env,
            pre_run_deps,
            trace_file,
            wpr_ready,
        } in requests
        {
            ctx.emit_rust_step("manage WPR tracing session", |ctx| {
                let session_name = session_name.clone();
                let extra_env = extra_env.claim(ctx);
                let pre_run_deps = pre_run_deps.claim(ctx);
                let trace_file = trace_file.claim(ctx);
                let wpr_ready = wpr_ready.claim(ctx);

                move |rt| {
                    // Wait for dependencies
                    for dep in pre_run_deps {
                        rt.read(dep);
                    }

                    // Read environment variables to get WPR configuration
                    let env = rt.read(extra_env);
                    
                    // Check if WPR tracing is enabled via environment variables
                    let wpr_enabled = env.get("OPENVMM_WPR_ENABLED")
                        .map(|v| v.to_lowercase() == "true" || v == "1")
                        .unwrap_or(false);
                    
                    if wpr_enabled {
                        log::info!("WPR tracing enabled for session: {}", session_name);
                        
                        // Create WPR configuration from environment
                        let wpr_profile = env.get("OPENVMM_WPR_PROFILE")
                            .map(|path| {
                                if path.is_empty() || path.to_lowercase() == "embedded" {
                                    crate::wpr_tracing::WprProfile::Embedded
                                } else {
                                    crate::wpr_tracing::WprProfile::Custom(PathBuf::from(path))
                                }
                            })
                            .unwrap_or(crate::wpr_tracing::WprProfile::Embedded);

                        let wpr_output_dir = env.get("OPENVMM_WPR_OUTPUT_DIR")
                            .map(PathBuf::from)
                            .unwrap_or_else(|| std::env::temp_dir().join("openvmm_wpr_traces"));

                        let config = crate::wpr_tracing::WprConfig {
                            enabled: true,
                            profile: wpr_profile,
                            output_dir: wpr_output_dir,
                        };
                        
                        // Create and start WPR session
                        let session = WprSession::new(session_name, config);
                        match session.start() {
                            Ok(()) => {
                                log::info!("WPR session started successfully");
                                
                                // Stop the session and get the trace file
                                let trace_result = session.stop();
                                match trace_result {
                                    Ok(Some(etl_file)) => {
                                        log::info!("WPR trace saved to: {}", etl_file.display());
                                        if let Some(trace_file) = trace_file {
                                            rt.write(trace_file, &Some(etl_file));
                                        }
                                    }
                                    Ok(None) => {
                                        log::warn!("WPR session stopped but no trace file generated");
                                        if let Some(trace_file) = trace_file {
                                            rt.write(trace_file, &None);
                                        }
                                    }
                                    Err(e) => {
                                        log::error!("Failed to stop WPR session: {}", e);
                                        if let Some(trace_file) = trace_file {
                                            rt.write(trace_file, &None);
                                        }
                                    }
                                }
                            }
                            Err(e) => {
                                log::error!("Failed to start WPR session: {}", e);
                                if let Some(trace_file) = trace_file {
                                    rt.write(trace_file, &None);
                                }
                            }
                        }
                    } else {
                        log::debug!("WPR tracing disabled");
                        if let Some(trace_file) = trace_file {
                            rt.write(trace_file, &None);
                        }
                    }

                    // Signal that WPR setup is complete
                    rt.write(wpr_ready, &());
                    
                    Ok(())
                }
            });
        }

        Ok(())
    }
}