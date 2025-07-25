"""
@generated by mypy-protobuf.  Do not edit manually!
isort:skip_file
Use proto3 as the older protobuf we need for centos doesn't support
2023 edition.
"""
import builtins
import collections.abc
import google.protobuf.descriptor
import google.protobuf.internal.containers
import google.protobuf.message
import sys

if sys.version_info >= (3, 8):
    import typing as typing_extensions
else:
    import typing_extensions

DESCRIPTOR: google.protobuf.descriptor.FileDescriptor

class InfoRequest(google.protobuf.message.Message):
    """--- Info ---
    Provide version numbers and basic information about the samba
    container instance. Mainly for debugging.
    """

    DESCRIPTOR: google.protobuf.descriptor.Descriptor

    def __init__(
        self,
    ) -> None: ...

global___InfoRequest = InfoRequest

class SambaInfo(google.protobuf.message.Message):
    DESCRIPTOR: google.protobuf.descriptor.Descriptor

    VERSION_FIELD_NUMBER: builtins.int
    CLUSTERED_FIELD_NUMBER: builtins.int
    version: builtins.str
    clustered: builtins.bool
    def __init__(
        self,
        *,
        version: builtins.str = ...,
        clustered: builtins.bool = ...,
    ) -> None: ...
    def ClearField(self, field_name: typing_extensions.Literal["clustered", b"clustered", "version", b"version"]) -> None: ...

global___SambaInfo = SambaInfo

class SambaContainerInfo(google.protobuf.message.Message):
    DESCRIPTOR: google.protobuf.descriptor.Descriptor

    SAMBACC_VERSION_FIELD_NUMBER: builtins.int
    CONTAINER_VERSION_FIELD_NUMBER: builtins.int
    sambacc_version: builtins.str
    container_version: builtins.str
    def __init__(
        self,
        *,
        sambacc_version: builtins.str = ...,
        container_version: builtins.str = ...,
    ) -> None: ...
    def ClearField(self, field_name: typing_extensions.Literal["container_version", b"container_version", "sambacc_version", b"sambacc_version"]) -> None: ...

global___SambaContainerInfo = SambaContainerInfo

class GeneralInfo(google.protobuf.message.Message):
    DESCRIPTOR: google.protobuf.descriptor.Descriptor

    SAMBA_INFO_FIELD_NUMBER: builtins.int
    CONTAINER_INFO_FIELD_NUMBER: builtins.int
    @property
    def samba_info(self) -> global___SambaInfo: ...
    @property
    def container_info(self) -> global___SambaContainerInfo: ...
    def __init__(
        self,
        *,
        samba_info: global___SambaInfo | None = ...,
        container_info: global___SambaContainerInfo | None = ...,
    ) -> None: ...
    def HasField(self, field_name: typing_extensions.Literal["container_info", b"container_info", "samba_info", b"samba_info"]) -> builtins.bool: ...
    def ClearField(self, field_name: typing_extensions.Literal["container_info", b"container_info", "samba_info", b"samba_info"]) -> None: ...

global___GeneralInfo = GeneralInfo

class StatusRequest(google.protobuf.message.Message):
    """--- Status ---
    Fetch status information from the samba instance. Includes basic
    information about connected clients.
    """

    DESCRIPTOR: google.protobuf.descriptor.Descriptor

    def __init__(
        self,
    ) -> None: ...

global___StatusRequest = StatusRequest

class SessionCrypto(google.protobuf.message.Message):
    DESCRIPTOR: google.protobuf.descriptor.Descriptor

    CIPHER_FIELD_NUMBER: builtins.int
    DEGREE_FIELD_NUMBER: builtins.int
    cipher: builtins.str
    degree: builtins.str
    def __init__(
        self,
        *,
        cipher: builtins.str = ...,
        degree: builtins.str = ...,
    ) -> None: ...
    def ClearField(self, field_name: typing_extensions.Literal["cipher", b"cipher", "degree", b"degree"]) -> None: ...

global___SessionCrypto = SessionCrypto

class SessionInfo(google.protobuf.message.Message):
    DESCRIPTOR: google.protobuf.descriptor.Descriptor

    SESSION_ID_FIELD_NUMBER: builtins.int
    USERNAME_FIELD_NUMBER: builtins.int
    GROUPNAME_FIELD_NUMBER: builtins.int
    REMOTE_MACHINE_FIELD_NUMBER: builtins.int
    HOSTNAME_FIELD_NUMBER: builtins.int
    SESSION_DIALECT_FIELD_NUMBER: builtins.int
    UID_FIELD_NUMBER: builtins.int
    GID_FIELD_NUMBER: builtins.int
    ENCRYPTION_FIELD_NUMBER: builtins.int
    SIGNING_FIELD_NUMBER: builtins.int
    session_id: builtins.str
    username: builtins.str
    groupname: builtins.str
    remote_machine: builtins.str
    hostname: builtins.str
    session_dialect: builtins.str
    uid: builtins.int
    gid: builtins.int
    @property
    def encryption(self) -> global___SessionCrypto: ...
    @property
    def signing(self) -> global___SessionCrypto: ...
    def __init__(
        self,
        *,
        session_id: builtins.str = ...,
        username: builtins.str = ...,
        groupname: builtins.str = ...,
        remote_machine: builtins.str = ...,
        hostname: builtins.str = ...,
        session_dialect: builtins.str = ...,
        uid: builtins.int = ...,
        gid: builtins.int = ...,
        encryption: global___SessionCrypto | None = ...,
        signing: global___SessionCrypto | None = ...,
    ) -> None: ...
    def HasField(self, field_name: typing_extensions.Literal["encryption", b"encryption", "signing", b"signing"]) -> builtins.bool: ...
    def ClearField(self, field_name: typing_extensions.Literal["encryption", b"encryption", "gid", b"gid", "groupname", b"groupname", "hostname", b"hostname", "remote_machine", b"remote_machine", "session_dialect", b"session_dialect", "session_id", b"session_id", "signing", b"signing", "uid", b"uid", "username", b"username"]) -> None: ...

global___SessionInfo = SessionInfo

class ConnInfo(google.protobuf.message.Message):
    DESCRIPTOR: google.protobuf.descriptor.Descriptor

    TCON_ID_FIELD_NUMBER: builtins.int
    SESSION_ID_FIELD_NUMBER: builtins.int
    SERVICE_NAME_FIELD_NUMBER: builtins.int
    tcon_id: builtins.str
    session_id: builtins.str
    service_name: builtins.str
    def __init__(
        self,
        *,
        tcon_id: builtins.str = ...,
        session_id: builtins.str = ...,
        service_name: builtins.str = ...,
    ) -> None: ...
    def ClearField(self, field_name: typing_extensions.Literal["service_name", b"service_name", "session_id", b"session_id", "tcon_id", b"tcon_id"]) -> None: ...

global___ConnInfo = ConnInfo

class StatusInfo(google.protobuf.message.Message):
    DESCRIPTOR: google.protobuf.descriptor.Descriptor

    SERVER_TIMESTAMP_FIELD_NUMBER: builtins.int
    SESSIONS_FIELD_NUMBER: builtins.int
    TREE_CONNECTIONS_FIELD_NUMBER: builtins.int
    server_timestamp: builtins.str
    @property
    def sessions(self) -> google.protobuf.internal.containers.RepeatedCompositeFieldContainer[global___SessionInfo]: ...
    @property
    def tree_connections(self) -> google.protobuf.internal.containers.RepeatedCompositeFieldContainer[global___ConnInfo]: ...
    def __init__(
        self,
        *,
        server_timestamp: builtins.str = ...,
        sessions: collections.abc.Iterable[global___SessionInfo] | None = ...,
        tree_connections: collections.abc.Iterable[global___ConnInfo] | None = ...,
    ) -> None: ...
    def ClearField(self, field_name: typing_extensions.Literal["server_timestamp", b"server_timestamp", "sessions", b"sessions", "tree_connections", b"tree_connections"]) -> None: ...

global___StatusInfo = StatusInfo

class CloseShareRequest(google.protobuf.message.Message):
    """--- CloseShare ---
    Close shares to clients.
    """

    DESCRIPTOR: google.protobuf.descriptor.Descriptor

    SHARE_NAME_FIELD_NUMBER: builtins.int
    DENIED_USERS_FIELD_NUMBER: builtins.int
    share_name: builtins.str
    denied_users: builtins.bool
    def __init__(
        self,
        *,
        share_name: builtins.str = ...,
        denied_users: builtins.bool = ...,
    ) -> None: ...
    def ClearField(self, field_name: typing_extensions.Literal["denied_users", b"denied_users", "share_name", b"share_name"]) -> None: ...

global___CloseShareRequest = CloseShareRequest

class CloseShareInfo(google.protobuf.message.Message):
    DESCRIPTOR: google.protobuf.descriptor.Descriptor

    def __init__(
        self,
    ) -> None: ...

global___CloseShareInfo = CloseShareInfo

class KillClientRequest(google.protobuf.message.Message):
    """--- KillClientConnection ---
    Forcibly disconnect a client.
    """

    DESCRIPTOR: google.protobuf.descriptor.Descriptor

    IP_ADDRESS_FIELD_NUMBER: builtins.int
    ip_address: builtins.str
    def __init__(
        self,
        *,
        ip_address: builtins.str = ...,
    ) -> None: ...
    def ClearField(self, field_name: typing_extensions.Literal["ip_address", b"ip_address"]) -> None: ...

global___KillClientRequest = KillClientRequest

class KillClientInfo(google.protobuf.message.Message):
    DESCRIPTOR: google.protobuf.descriptor.Descriptor

    def __init__(
        self,
    ) -> None: ...

global___KillClientInfo = KillClientInfo
