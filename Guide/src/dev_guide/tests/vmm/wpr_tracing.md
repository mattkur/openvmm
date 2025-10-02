# WPR Tracing Integration

OpenVMM VMM tests support automatic collection of WPR (Windows Performance Record) ETL traces for debugging and performance analysis.

## Overview

WPR tracing captures detailed information about the OpenVMM/OpenHCL/Hyper-V virtualization stack during test execution. This is particularly useful for:

- Performance analysis and optimization
- Debugging complex virtualization issues
- Understanding system behavior under test scenarios
- Collecting diagnostic information for CI/CD pipelines

## Configuration

WPR tracing is **disabled by default** and must be explicitly enabled via environment variables:

### Environment Variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `OPENVMM_WPR_ENABLED` | Boolean | `false` | Enable/disable WPR tracing |
| `OPENVMM_WPR_PROFILE` | String | `embedded` | WPR profile to use |
| `OPENVMM_WPR_OUTPUT_DIR` | Path | `%TEMP%\openvmm_wpr_traces` | Output directory for ETL files |

### Profile Options

- **`embedded`** (default): Uses built-in profile targeting OpenVMM/OpenHCL/Hyper-V providers
- **Custom path**: Path to a custom WPR profile file (`.wprp`)

## Usage Examples

### Basic Usage

```bash
# Enable WPR tracing with embedded profile
export OPENVMM_WPR_ENABLED=true

# Run VMM tests as usual
cargo test --package vmm_tests
```

### Custom Profile

```bash
# Use custom WPR profile
export OPENVMM_WPR_ENABLED=true
export OPENVMM_WPR_PROFILE=C:\path\to\custom.wprp

# Run specific test
cargo test --package vmm_tests test_name
```

### Custom Output Directory

```bash
# Specify custom output directory
export OPENVMM_WPR_ENABLED=true
export OPENVMM_WPR_OUTPUT_DIR=C:\traces\vmm_tests

# Run tests
cargo test --package vmm_tests
```

## Embedded Profile

The embedded WPR profile includes providers for:

- **System Events**: Process/thread lifecycle, context switches, DPC/ISR
- **Memory Events**: Virtual memory allocation, page faults
- **Hyper-V Events**: VM lifecycle, hypervisor kernel events
- **Virtualization Stack**: OpenVMM/OpenHCL specific events

## ETL File Collection

ETL files are automatically collected as test artifacts:

1. WPR session starts before test execution
2. Test runs with tracing enabled
3. WPR session stops after test completion  
4. ETL file is copied to test output directory
5. File is marked as test attachment for CI/CD systems

Files are named using the pattern: `{test_session_name}.etl`

## Platform Support

- **Windows**: Full WPR tracing support
- **Linux/macOS**: Configuration is parsed but tracing is gracefully skipped

## Troubleshooting

### Common Issues

1. **WPR not found**: Install Windows Performance Toolkit (part of Windows SDK)
2. **Permission errors**: Run with administrator privileges
3. **Profile errors**: Verify custom profile file exists and is valid WPR XML
4. **Large ETL files**: Consider using custom profiles to reduce data collection

### Debug Information

Enable debug logging to see WPR tracing status:

```bash
export RUST_LOG=debug
export OPENVMM_LOG=debug
```

Look for log messages like:
- `WPR tracing enabled for session: vmm_tests`
- `WPR session started successfully`
- `WPR trace saved to: {path}`

## CI/CD Integration

WPR tracing works seamlessly with CI/CD pipelines:

```yaml
# Azure DevOps example
- task: PowerShell@2
  displayName: 'Run VMM Tests with WPR Tracing'
  env:
    OPENVMM_WPR_ENABLED: true
    OPENVMM_WPR_PROFILE: embedded
  script: |
    cargo test --package vmm_tests

- task: PublishBuildArtifacts@1
  displayName: 'Publish ETL Files'
  inputs:
    pathToPublish: $(Agent.TempDirectory)\wpr_traces
    artifactName: wpr_traces
```

## Performance Considerations

- ETL files can be large (10MB-1GB+ depending on test duration)
- Custom profiles can reduce file size by filtering events
- Consider enabling only for specific test scenarios or CI builds
- Files are automatically cleaned up after test completion

## Best Practices

1. **Enable selectively**: Only enable WPR tracing when needed for debugging
2. **Use custom profiles**: Create targeted profiles for specific analysis needs
3. **Monitor file sizes**: Large ETL files can impact test performance
4. **Clean up regularly**: ETL files accumulate in output directories
5. **Archive traces**: Keep traces for failed tests, clean up successful ones