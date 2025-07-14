// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

//! Windows Performance Record (WPR) tracing support for VMM tests.
//!
//! This module provides functionality to start/stop WPR trace sessions
//! during test execution and collect the resulting ETL files as test artifacts.

use flowey::node::prelude::*;
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

/// Configuration for WPR tracing
#[derive(Debug, Clone)]
pub struct WprConfig {
    /// Enable WPR tracing
    pub enabled: bool,
    /// WPR profile to use (embedded or path to profile file)
    pub profile: WprProfile,
    /// Output directory for ETL files
    pub output_dir: PathBuf,
}

/// WPR profile configuration
#[derive(Debug, Clone)]
pub enum WprProfile {
    /// Use embedded OpenVMM/OpenHCL/Hyper-V profile
    Embedded,
    /// Use custom profile file
    Custom(PathBuf),
}

/// WPR session management
pub struct WprSession {
    session_name: String,
    output_file: PathBuf,
    config: WprConfig,
}

impl WprSession {
    /// Create a new WPR session
    pub fn new(session_name: String, config: WprConfig) -> Self {
        let output_file = config.output_dir.join(format!("{}.etl", session_name));
        Self {
            session_name,
            output_file,
            config,
        }
    }

    /// Start WPR tracing session
    pub fn start(&self) -> anyhow::Result<()> {
        if !self.config.enabled {
            return Ok(());
        }

        // Only run on Windows
        if !cfg!(windows) {
            log::debug!("WPR tracing only supported on Windows, skipping");
            return Ok(());
        }

        // Ensure output directory exists
        if let Some(parent) = self.output_file.parent() {
            std::fs::create_dir_all(parent)?;
        }

        let profile_arg = match &self.config.profile {
            WprProfile::Embedded => {
                // Use embedded profile targeting OpenVMM/OpenHCL/Hyper-V
                self.get_embedded_profile_path()?
            }
            WprProfile::Custom(path) => path.to_string_lossy().to_string(),
        };

        log::info!("Starting WPR session: {}", self.session_name);
        
        let output = std::process::Command::new("wpr")
            .args(&[
                "-start",
                &profile_arg,
                "-filemode",
                "-instancename",
                &self.session_name,
            ])
            .output()?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            anyhow::bail!("Failed to start WPR session: {}", stderr);
        }

        log::debug!("WPR session started successfully");
        Ok(())
    }

    /// Stop WPR tracing session and save ETL file
    pub fn stop(&self) -> anyhow::Result<Option<PathBuf>> {
        if !self.config.enabled {
            return Ok(None);
        }

        if !cfg!(windows) {
            return Ok(None);
        }

        log::info!("Stopping WPR session: {}", self.session_name);

        let output = std::process::Command::new("wpr")
            .args(&[
                "-stop",
                &self.output_file.to_string_lossy(),
                "-instancename", 
                &self.session_name,
            ])
            .output()?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            log::warn!("Failed to stop WPR session: {}", stderr);
            return Ok(None);
        }

        if self.output_file.exists() {
            log::info!("WPR trace saved to: {}", self.output_file.display());
            Ok(Some(self.output_file.clone()))
        } else {
            log::warn!("WPR trace file not found after stopping session");
            Ok(None)
        }
    }

    fn get_embedded_profile_path(&self) -> anyhow::Result<String> {
        // Create a temporary WPR profile file with OpenVMM/OpenHCL/Hyper-V specific providers
        let temp_dir = std::env::temp_dir();
        let profile_path = temp_dir.join("openvmm_wpr_profile.wprp");
        
        let profile_content = r#"<?xml version="1.0" encoding="utf-8"?>
<WindowsPerformanceRecorder Version="1.0" Author="OpenVMM" Team="OpenVMM">
  <Profiles>
    <SystemCollector Id="SystemCollector_OpenVMM" Name="NT Kernel Logger">
      <BufferSize Value="1024"/>
      <Buffers Value="100"/>
    </SystemCollector>
    
    <EventCollector Id="EventCollector_OpenVMM" Name="OpenVMM Event Collector">
      <BufferSize Value="1024"/>
      <Buffers Value="100"/>
    </EventCollector>
    
    <SystemProvider Id="SystemProvider_OpenVMM">
      <Keywords>
        <Keyword Value="ProcessThread"/>
        <Keyword Value="Loader"/>
        <Keyword Value="CSwitch"/>
        <Keyword Value="Interrupt"/>
        <Keyword Value="DPC"/>
        <Keyword Value="SampledProfile"/>
        <Keyword Value="VirtualAlloc"/>
        <Keyword Value="Memory"/>
        <Keyword Value="HypervisorKernel"/>
        <Keyword Value="HypervisorUser"/>
      </Keywords>
      <Stacks>
        <Stack Value="CSwitch"/>
        <Stack Value="ReadyThread"/>
        <Stack Value="VirtualAlloc"/>
      </Stacks>
    </SystemProvider>
    
    <EventProvider Id="Microsoft-Windows-Hyper-V-VmsIf" Name="Microsoft-Windows-Hyper-V-VmsIf">
      <Keywords>
        <Keyword Value="0xFFFFFFFF"/>
      </Keywords>
    </EventProvider>
    
    <EventProvider Id="Microsoft-Windows-Hyper-V-Hypervisor" Name="Microsoft-Windows-Hyper-V-Hypervisor">
      <Keywords>
        <Keyword Value="0xFFFFFFFF"/>
      </Keywords>
    </EventProvider>
    
    <EventProvider Id="Microsoft-Windows-Hyper-V-VID" Name="Microsoft-Windows-Hyper-V-VID">
      <Keywords>
        <Keyword Value="0xFFFFFFFF"/>
      </Keywords>
    </EventProvider>
    
    <Profile Id="OpenVMM_VirtStack.Verbose.File" Name="OpenVMM_VirtStack" Description="OpenVMM/OpenHCL/Hyper-V Virtualization Stack Trace" LoggingMode="File" DetailLevel="Verbose">
      <Collectors>
        <SystemCollectorId Value="SystemCollector_OpenVMM">
          <SystemProviderId Value="SystemProvider_OpenVMM"/>
        </SystemCollectorId>
        <EventCollectorId Value="EventCollector_OpenVMM">
          <EventProviders>
            <EventProviderId Value="Microsoft-Windows-Hyper-V-VmsIf"/>
            <EventProviderId Value="Microsoft-Windows-Hyper-V-Hypervisor"/>
            <EventProviderId Value="Microsoft-Windows-Hyper-V-VID"/>
          </EventProviders>
        </EventCollectorId>
      </Collectors>
    </Profile>
  </Profiles>
</WindowsPerformanceRecorder>"#;

        std::fs::write(&profile_path, profile_content)?;
        Ok(profile_path.to_string_lossy().to_string())
    }
}

/// Get WPR configuration from environment variables
pub fn get_wpr_config_from_env() -> WprConfig {
    let enabled = std::env::var("OPENVMM_WPR_ENABLED")
        .map(|v| v.to_lowercase() == "true" || v == "1")
        .unwrap_or(false);

    let profile = std::env::var("OPENVMM_WPR_PROFILE")
        .map(|path| {
            if path.is_empty() || path.to_lowercase() == "embedded" {
                WprProfile::Embedded
            } else {
                WprProfile::Custom(PathBuf::from(path))
            }
        })
        .unwrap_or(WprProfile::Embedded);

    let output_dir = std::env::var("OPENVMM_WPR_OUTPUT_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|_| std::env::temp_dir().join("openvmm_wpr_traces"));

    WprConfig {
        enabled,
        profile,
        output_dir,
    }
}

/// Add WPR tracing environment variables to test environment
pub fn add_wpr_env_vars(env: &mut BTreeMap<String, String>, test_output_dir: &Path) {
    // Set default WPR output directory to the test output directory
    if !env.contains_key("OPENVMM_WPR_OUTPUT_DIR") {
        env.insert(
            "OPENVMM_WPR_OUTPUT_DIR".to_string(),
            test_output_dir.join("wpr_traces").to_string_lossy().to_string(),
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::env;

    #[test]
    fn test_wpr_config_from_env() {
        // Test disabled by default
        let config = get_wpr_config_from_env();
        assert!(!config.enabled);
        assert!(matches!(config.profile, WprProfile::Embedded));

        // Test enabled
        // TODO: Audit that the environment access only happens in single-threaded code.
        unsafe { env::set_var("OPENVMM_WPR_ENABLED", "true") };
        let config = get_wpr_config_from_env();
        assert!(config.enabled);
        // TODO: Audit that the environment access only happens in single-threaded code.
        unsafe { env::remove_var("OPENVMM_WPR_ENABLED") };

        // Test custom profile
        // TODO: Audit that the environment access only happens in single-threaded code.
        unsafe { env::set_var("OPENVMM_WPR_PROFILE", "/path/to/profile.wprp") };
        let config = get_wpr_config_from_env();
        assert!(matches!(config.profile, WprProfile::Custom(_)));
        // TODO: Audit that the environment access only happens in single-threaded code.
        unsafe { env::remove_var("OPENVMM_WPR_PROFILE") };
    }

    #[test]
    fn test_wpr_session_creation() {
        let config = WprConfig {
            enabled: true,
            profile: WprProfile::Embedded,
            output_dir: PathBuf::from("/tmp/traces"),
        };

        let session = WprSession::new("test_session".to_string(), config);
        assert_eq!(session.session_name, "test_session");
        assert_eq!(session.output_file, PathBuf::from("/tmp/traces/test_session.etl"));
    }
}