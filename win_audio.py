"""
Windows audio default device helpers.

This module uses Core Audio COM interfaces through ctypes to:
- enumerate active render/capture endpoints
- set the system default endpoint for Console/Multimedia/Communications roles
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from uuid import UUID


DEVICE_STATE_ACTIVE = 0x00000001
E_RENDER = 0
E_CAPTURE = 1
ERole_CONSOLE = 0
ERole_MULTIMEDIA = 1
ERole_COMMUNICATIONS = 2
CLSCTX_ALL = 23
STGM_READ = 0


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", GUID), ("pid", wintypes.DWORD)]


class PROPVARIANT_UNION(ctypes.Union):
    _fields_ = [
        ("llVal", ctypes.c_longlong),
        ("lVal", ctypes.c_long),
        ("bstrVal", wintypes.LPWSTR),
        ("pwszVal", wintypes.LPWSTR),
    ]


class PROPVARIANT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [
        ("vt", wintypes.USHORT),
        ("wReserved1", wintypes.USHORT),
        ("wReserved2", wintypes.USHORT),
        ("wReserved3", wintypes.USHORT),
        ("u", PROPVARIANT_UNION),
    ]


class IUnknownVTBL(ctypes.Structure):
    _fields_ = [
        ("QueryInterface", ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))),
        ("AddRef", ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)),
        ("Release", ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)),
    ]


class IMMDeviceEnumeratorVTBL(ctypes.Structure):
    _fields_ = [
        ("QueryInterface", IUnknownVTBL._fields_[0][1]),
        ("AddRef", IUnknownVTBL._fields_[1][1]),
        ("Release", IUnknownVTBL._fields_[2][1]),
        ("EnumAudioEndpoints", ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_int, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p))),
        ("GetDefaultAudioEndpoint", ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))),
        ("GetDevice", ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p))),
        ("RegisterEndpointNotificationCallback", ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p)),
        ("UnregisterEndpointNotificationCallback", ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p)),
    ]


class IMMDeviceCollectionVTBL(ctypes.Structure):
    _fields_ = [
        ("QueryInterface", IUnknownVTBL._fields_[0][1]),
        ("AddRef", IUnknownVTBL._fields_[1][1]),
        ("Release", IUnknownVTBL._fields_[2][1]),
        ("GetCount", ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(wintypes.UINT))),
        ("Item", ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p))),
    ]


class IMMDeviceVTBL(ctypes.Structure):
    _fields_ = [
        ("QueryInterface", IUnknownVTBL._fields_[0][1]),
        ("AddRef", IUnknownVTBL._fields_[1][1]),
        ("Release", IUnknownVTBL._fields_[2][1]),
        ("Activate", ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(GUID), wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))),
        ("OpenPropertyStore", ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p))),
        ("GetId", ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR))),
        ("GetState", ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD))),
    ]


class IPropertyStoreVTBL(ctypes.Structure):
    _fields_ = [
        ("QueryInterface", IUnknownVTBL._fields_[0][1]),
        ("AddRef", IUnknownVTBL._fields_[1][1]),
        ("Release", IUnknownVTBL._fields_[2][1]),
        ("GetCount", ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD))),
        ("GetAt", ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(PROPERTYKEY))),
        ("GetValue", ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(PROPERTYKEY), ctypes.POINTER(PROPVARIANT))),
        ("SetValue", ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(PROPERTYKEY), ctypes.POINTER(PROPVARIANT))),
        ("Commit", ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)),
    ]


class IPolicyConfigVTBL(ctypes.Structure):
    _fields_ = [
        ("QueryInterface", IUnknownVTBL._fields_[0][1]),
        ("AddRef", IUnknownVTBL._fields_[1][1]),
        ("Release", IUnknownVTBL._fields_[2][1]),
        ("GetMixFormat", ctypes.c_void_p),
        ("GetDeviceFormat", ctypes.c_void_p),
        ("ResetDeviceFormat", ctypes.c_void_p),
        ("SetDeviceFormat", ctypes.c_void_p),
        ("GetProcessingPeriod", ctypes.c_void_p),
        ("SetProcessingPeriod", ctypes.c_void_p),
        ("GetShareMode", ctypes.c_void_p),
        ("SetShareMode", ctypes.c_void_p),
        ("GetPropertyValue", ctypes.c_void_p),
        ("SetPropertyValue", ctypes.c_void_p),
        ("SetDefaultEndpoint", ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.LPCWSTR, ctypes.c_int)),
        ("SetEndpointVisibility", ctypes.c_void_p),
    ]


class _COMInterface(ctypes.Structure):
    _fields_ = [("lpVtbl", ctypes.c_void_p)]


def _guid(text: str) -> GUID:
    u = UUID(text)
    data4 = (ctypes.c_ubyte * 8)(*u.bytes[8:16])
    return GUID(u.time_low, u.time_mid, u.time_hi_version, data4)


def _check(hr: int, msg: str) -> None:
    if hr < 0:
        raise OSError(f"{msg} failed (HRESULT=0x{hr & 0xFFFFFFFF:08X})")


def _vtable(obj_ptr: ctypes.c_void_p, vtbl_cls):
    iface = ctypes.cast(obj_ptr, ctypes.POINTER(_COMInterface)).contents
    return ctypes.cast(iface.lpVtbl, ctypes.POINTER(vtbl_cls)).contents


def _release(obj_ptr: ctypes.c_void_p | None) -> None:
    if not obj_ptr:
        return
    vtbl = _vtable(obj_ptr, IUnknownVTBL)
    vtbl.Release(obj_ptr)


def _propvariant_clear(value: PROPVARIANT) -> None:
    ole32 = ctypes.windll.ole32
    ole32.PropVariantClear.argtypes = [ctypes.POINTER(PROPVARIANT)]
    ole32.PropVariantClear.restype = ctypes.c_long
    ole32.PropVariantClear(ctypes.byref(value))


def _co_task_mem_free(ptr: ctypes.c_void_p) -> None:
    if ptr:
        ctypes.windll.ole32.CoTaskMemFree(ptr)


def enumerate_audio_endpoints(flow: str) -> list[tuple[str, str]]:
    if flow not in ("render", "capture"):
        raise ValueError("flow must be 'render' or 'capture'")

    e_data_flow = E_RENDER if flow == "render" else E_CAPTURE
    clsid_enumerator = _guid("BCDE0395-E52F-467C-8E3D-C4579291692E")
    iid_enumerator = _guid("A95664D2-9614-4F35-A746-DE8DB63617E6")
    iid_property_store = _guid("886d8eeb-8cf2-4446-8d02-cdba1dbdcf99")
    pkey_friendly_name = PROPERTYKEY(
        _guid("a45c254e-df1c-4efd-8020-67d146a850e0"),
        14,
    )

    ole32 = ctypes.windll.ole32
    ole32.CoInitialize.argtypes = [ctypes.c_void_p]
    ole32.CoInitialize.restype = ctypes.c_long
    ole32.CoUninitialize.argtypes = []

    init_hr = ole32.CoInitialize(None)
    if init_hr < 0:
        _check(init_hr, "CoInitialize")

    enumerator = ctypes.c_void_p()
    collection = ctypes.c_void_p()
    endpoints: list[tuple[str, str]] = []

    try:
        ole32.CoCreateInstance.argtypes = [
            ctypes.POINTER(GUID),
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(GUID),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        ole32.CoCreateInstance.restype = ctypes.c_long

        hr = ole32.CoCreateInstance(
            ctypes.byref(clsid_enumerator),
            None,
            CLSCTX_ALL,
            ctypes.byref(iid_enumerator),
            ctypes.byref(enumerator),
        )
        _check(hr, "CoCreateInstance(IMMDeviceEnumerator)")

        enum_vtbl = _vtable(enumerator, IMMDeviceEnumeratorVTBL)
        hr = enum_vtbl.EnumAudioEndpoints(enumerator, e_data_flow, DEVICE_STATE_ACTIVE, ctypes.byref(collection))
        _check(hr, "EnumAudioEndpoints")

        coll_vtbl = _vtable(collection, IMMDeviceCollectionVTBL)
        count = wintypes.UINT()
        hr = coll_vtbl.GetCount(collection, ctypes.byref(count))
        _check(hr, "IMMDeviceCollection.GetCount")

        for i in range(count.value):
            device = ctypes.c_void_p()
            prop_store = ctypes.c_void_p()
            dev_id = wintypes.LPWSTR()
            pv = PROPVARIANT()
            try:
                hr = coll_vtbl.Item(collection, i, ctypes.byref(device))
                _check(hr, "IMMDeviceCollection.Item")

                dev_vtbl = _vtable(device, IMMDeviceVTBL)
                hr = dev_vtbl.GetId(device, ctypes.byref(dev_id))
                _check(hr, "IMMDevice.GetId")

                hr = dev_vtbl.OpenPropertyStore(device, STGM_READ, ctypes.byref(prop_store))
                _check(hr, "IMMDevice.OpenPropertyStore")

                prop_vtbl = _vtable(prop_store, IPropertyStoreVTBL)
                hr = prop_vtbl.GetValue(prop_store, ctypes.byref(pkey_friendly_name), ctypes.byref(pv))
                _check(hr, "IPropertyStore.GetValue")

                friendly_name = pv.pwszVal or ""
                endpoint_id = dev_id.value or ""
                endpoints.append((endpoint_id, friendly_name))
            finally:
                _propvariant_clear(pv)
                if dev_id:
                    _co_task_mem_free(dev_id)
                _release(prop_store)
                _release(device)

        return endpoints
    finally:
        _release(collection)
        _release(enumerator)
        if init_hr >= 0:
            ole32.CoUninitialize()


def get_default_audio_device_name(flow: str) -> str:
    """Get current Windows default endpoint friendly name.

    Args:
        flow: "render" for output or "capture" for input.
    """
    if flow not in ("render", "capture"):
        raise ValueError("flow must be 'render' or 'capture'")

    e_data_flow = E_RENDER if flow == "render" else E_CAPTURE
    clsid_enumerator = _guid("BCDE0395-E52F-467C-8E3D-C4579291692E")
    iid_enumerator = _guid("A95664D2-9614-4F35-A746-DE8DB63617E6")
    pkey_friendly_name = PROPERTYKEY(
        _guid("a45c254e-df1c-4efd-8020-67d146a850e0"),
        14,
    )

    ole32 = ctypes.windll.ole32
    ole32.CoInitialize.argtypes = [ctypes.c_void_p]
    ole32.CoInitialize.restype = ctypes.c_long
    ole32.CoUninitialize.argtypes = []

    init_hr = ole32.CoInitialize(None)
    if init_hr < 0:
        _check(init_hr, "CoInitialize")

    enumerator = ctypes.c_void_p()
    device = ctypes.c_void_p()
    prop_store = ctypes.c_void_p()
    pv = PROPVARIANT()

    try:
        ole32.CoCreateInstance.argtypes = [
            ctypes.POINTER(GUID),
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(GUID),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        ole32.CoCreateInstance.restype = ctypes.c_long

        hr = ole32.CoCreateInstance(
            ctypes.byref(clsid_enumerator),
            None,
            CLSCTX_ALL,
            ctypes.byref(iid_enumerator),
            ctypes.byref(enumerator),
        )
        _check(hr, "CoCreateInstance(IMMDeviceEnumerator)")

        enum_vtbl = _vtable(enumerator, IMMDeviceEnumeratorVTBL)
        hr = enum_vtbl.GetDefaultAudioEndpoint(
            enumerator,
            e_data_flow,
            ERole_MULTIMEDIA,
            ctypes.byref(device),
        )
        _check(hr, "GetDefaultAudioEndpoint")

        dev_vtbl = _vtable(device, IMMDeviceVTBL)
        hr = dev_vtbl.OpenPropertyStore(device, STGM_READ, ctypes.byref(prop_store))
        _check(hr, "IMMDevice.OpenPropertyStore")

        prop_vtbl = _vtable(prop_store, IPropertyStoreVTBL)
        hr = prop_vtbl.GetValue(prop_store, ctypes.byref(pkey_friendly_name), ctypes.byref(pv))
        _check(hr, "IPropertyStore.GetValue")

        return pv.pwszVal or ""
    finally:
        _propvariant_clear(pv)
        _release(prop_store)
        _release(device)
        _release(enumerator)
        if init_hr >= 0:
            ole32.CoUninitialize()


def _set_default_audio_device_by_id(endpoint_id: str) -> None:
    clsid_policy = _guid("870af99c-171d-4f9e-af0d-e63df40c2bc9")
    iid_policy = _guid("f8679f50-850a-41cf-9c72-430f290290c8")

    ole32 = ctypes.windll.ole32
    ole32.CoInitialize.argtypes = [ctypes.c_void_p]
    ole32.CoInitialize.restype = ctypes.c_long
    ole32.CoUninitialize.argtypes = []

    init_hr = ole32.CoInitialize(None)
    if init_hr < 0:
        _check(init_hr, "CoInitialize")

    policy = ctypes.c_void_p()
    try:
        ole32.CoCreateInstance.argtypes = [
            ctypes.POINTER(GUID),
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(GUID),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        ole32.CoCreateInstance.restype = ctypes.c_long

        hr = ole32.CoCreateInstance(
            ctypes.byref(clsid_policy),
            None,
            CLSCTX_ALL,
            ctypes.byref(iid_policy),
            ctypes.byref(policy),
        )
        _check(hr, "CoCreateInstance(IPolicyConfig)")

        policy_vtbl = _vtable(policy, IPolicyConfigVTBL)
        for role in (ERole_CONSOLE, ERole_MULTIMEDIA, ERole_COMMUNICATIONS):
            hr = policy_vtbl.SetDefaultEndpoint(policy, endpoint_id, role)
            _check(hr, "IPolicyConfig.SetDefaultEndpoint")
    finally:
        _release(policy)
        if init_hr >= 0:
            ole32.CoUninitialize()


def set_default_audio_device_by_name(name: str, flow: str) -> None:
    """Set Windows default endpoint by exact friendly name.

    Args:
        name: Friendly device name shown by Windows.
        flow: "render" for output or "capture" for input.
    """
    endpoints = enumerate_audio_endpoints(flow)
    exact = [eid for eid, fname in endpoints if fname == name]
    if not exact:
        lower = name.strip().lower()
        exact = [eid for eid, fname in endpoints if fname.strip().lower() == lower]
    if not exact:
        raise ValueError(f"Audio endpoint not found: {name}")

    _set_default_audio_device_by_id(exact[0])
