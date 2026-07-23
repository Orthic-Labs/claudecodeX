# Give the claudecodex window its own taskbar button.
#
# Claude Desktop does not give the isolated instance a distinct app identity, so
# Windows groups both windows under one taskbar button. Windows DOES honour
# an explicit per-window AUMID set via SHGetPropertyStoreForWindow + PKEY_AppUserModel_ID.
#
# All COM work happens inside compiled C#: PowerShell cannot bind methods on the
# IPropertyStore it gets back (a bare __ComObject), so Commit() -- which persists the
# property -- silently fails from script. The AUMID lives on the HWND, so launch.ps1
# re-applies this on every start.

param(
    [Parameter(Mandatory)][int]$TargetPid,
    [string]$Aumid = 'claudecodex.Instance',
    [string]$DisplayName = 'claudecodex',
    [string]$IconResource = ''
)

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class WindowAumid
{
    [ComImport, Guid("886d8eeb-8cf2-4446-8d02-cdba1dbdcf99"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IPropertyStore
    {
        void GetCount(out uint cProps);
        void GetAt(uint iProp, out PropertyKey pkey);
        void GetValue(ref PropertyKey key, out PropVariant pv);
        void SetValue(ref PropertyKey key, ref PropVariant pv);
        void Commit();
    }

    [StructLayout(LayoutKind.Sequential, Pack = 4)]
    private struct PropertyKey { public Guid fmtid; public uint pid;
        public PropertyKey(Guid f, uint p) { fmtid = f; pid = p; } }

    [StructLayout(LayoutKind.Sequential)]
    private struct PropVariant { public ushort vt; public ushort r1, r2, r3;
        public IntPtr pointerValue; public IntPtr pad; }

    [DllImport("shell32.dll")]
    private static extern int SHGetPropertyStoreForWindow(
        IntPtr hwnd, ref Guid iid,
        [MarshalAs(UnmanagedType.Interface)] out IPropertyStore propertyStore);

    // InitPropVariantFromString is an INLINE propvarutil.h helper, NOT a DLL export
    // (P/Invoke throws EntryPointNotFound). Build the PROPVARIANT by hand: VT_LPWSTR.
    [DllImport("ole32.dll")]
    private static extern int PropVariantClear(ref PropVariant pv);

    private const ushort VT_LPWSTR = 31;

    // fmtid {9F4C2855-...}: 5=AppUserModel_ID  4=RelaunchDisplayName  3=RelaunchIcon
    private static readonly Guid FMTID = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3");

    private static void Set(IPropertyStore store, uint pid, string value)
    {
        PropVariant pv = new PropVariant();
        pv.vt = VT_LPWSTR;
        pv.pointerValue = Marshal.StringToCoTaskMemUni(value);
        try { PropertyKey key = new PropertyKey(FMTID, pid); store.SetValue(ref key, ref pv); }
        finally { PropVariantClear(ref pv); }
    }

    public static void Apply(IntPtr hwnd, string aumid, string displayName, string iconResource)
    {
        Guid iid = new Guid("886d8eeb-8cf2-4446-8d02-cdba1dbdcf99");
        IPropertyStore store;
        Marshal.ThrowExceptionForHR(SHGetPropertyStoreForWindow(hwnd, ref iid, out store));
        try
        {
            Set(store, 5, aumid);
            Set(store, 4, displayName);
            if (!string.IsNullOrEmpty(iconResource)) Set(store, 3, iconResource);
            store.Commit();
        }
        finally { Marshal.ReleaseComObject(store); }
    }
}
'@ -ErrorAction Stop

$proc = Get-Process -Id $TargetPid -ErrorAction Stop
$hwnd = $proc.MainWindowHandle
if ($hwnd -eq [IntPtr]::Zero) { throw "pid $TargetPid has no main window yet" }

[WindowAumid]::Apply($hwnd, $Aumid, $DisplayName, $IconResource)
Write-Host "[claudecodex] taskbar identity set: '$DisplayName' ($Aumid) on pid $TargetPid"
