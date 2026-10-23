"""Windows system commit is distinct from resident physical memory."""
import os


def commit_memory():
    if os.name!='nt':return None
    import ctypes
    from ctypes import wintypes
    class PerformanceInformation(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in
            ('CommitTotal','CommitLimit','CommitPeak','PhysicalTotal','PhysicalAvailable',
             'SystemCache','KernelTotal','KernelPaged','KernelNonpaged','PageSize')]+[
            (name,wintypes.DWORD) for name in ('HandleCount','ProcessCount','ThreadCount')]
    try:
        info=PerformanceInformation();info.cb=ctypes.sizeof(info)
        function=ctypes.WinDLL('psapi',use_last_error=True).GetPerformanceInfo
        function.argtypes=[ctypes.POINTER(PerformanceInformation),wintypes.DWORD];function.restype=wintypes.BOOL
        if not function(ctypes.byref(info),info.cb):raise ctypes.WinError(ctypes.get_last_error())
        if not info.PageSize or not info.CommitLimit or info.CommitTotal>info.CommitLimit:
            raise ValueError('Invalid Windows system commit counters')
        return dict(status='measured',limit_bytes=info.CommitLimit*info.PageSize,
            used_bytes=info.CommitTotal*info.PageSize,available_bytes=(info.CommitLimit-info.CommitTotal)*info.PageSize,
            method='Windows GetPerformanceInfo; committed pages, separate from resident physical RAM')
    except (OSError,ValueError,AttributeError) as exc:
        return dict(status='unavailable',reason=str(exc))
