"""Actual observed failure signatures; no fabricated successful Editor output."""
from engines.editor_recovery import prepare_retry


def test_upm_ipc_retry_is_bounded_and_archives_the_failure(tmp_path):
    log=tmp_path/'unity.log';text='IPCStream (Upm-4496): IPC stream failed to read (Not connected)\n[Package Manager] Failed to resolve packages: operation cancelled.'
    log.write_text(text,'utf-8');command=['Unity.exe','-nographics','-logFile',str(log)]
    assert prepare_retry(tmp_path,command,'animation_native_import')
    assert (tmp_path/'animation_native_import.failed_startup.log').read_text('utf-8')==text
    assert not prepare_retry(tmp_path,command,'animation_native_import')
    assert command==['Unity.exe','-nographics','-logFile',str(log)]


def test_editor_content_and_license_errors_are_not_blindly_retried(tmp_path):
    log=tmp_path/'unity.log';command=['Unity.exe','-logFile',str(log)]
    for text in ['error CS1002: missing semicolon','License entitlement denied','out of memory','IPC stream failed to read (Not connected)',
        'IPC stream failed to read (Not connected)\nFailed to resolve packages: operation cancelled.\nerror CS1002']:
        log.write_text(text,'utf-8');assert not prepare_retry(tmp_path,command,'test')
    assert not (tmp_path/'editor_startup_recovery.json').exists()
