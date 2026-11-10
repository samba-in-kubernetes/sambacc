import io
import pathlib

import pytest

import sambacc.krbconf

krb5_main = """\
# main config
includedir /etc/krb5.conf.d/

[libdefaults]
    default_realm = DOM1.SINK.TEST
    dns_lookup_kdc = false
; another comment
[realms]
    DOM1.SINK.TEST = {
        kdc = kdc1.dom1.sink.test
        kdc = "kdc2.dom1.sink.test"
        v4_name_convert = {
            host = {
                rcmd = host
            }
        }
    }

[domain_realm]
    .dom1.sink.test = DOM1.SINK.TEST
"""

krb5_extra = """\
[libdefaults]
    forwardable = true

[realms]
    OTHER.ORG = {
        admin_server = admin.other.org
    }
"""

krb5_enctypes = """\
[libdefaults]
permitted_enctypes = aes256-cts-hmac-sha384-192 aes128-cts-hmac-sha256-128
"""


def _load(text):
    kf = sambacc.krbconf.KrbConfLoader("test")
    kf.readfp(io.StringIO(text))
    return kf


def _write_confs(tmp_path, crypto_policies=False):
    out = []
    main = tmp_path / "krb5.conf"
    main.write_text(krb5_main)
    out.append(main)
    cdir = tmp_path / "krb5.conf.d"
    cdir.mkdir()
    extra_conf = cdir / "extra.conf"
    extra_conf.write_text(krb5_extra)
    out.append(extra_conf)
    if crypto_policies:
        cpol = cdir / "crypto-policies"
        cpol.write_text(krb5_enctypes)
        out.append(cpol)
    return out


def test_parse_sections():
    kf = _load(krb5_main)
    assert list(kf.sections) == ["libdefaults", "realms", "domain_realm"]
    assert kf.sections["libdefaults"].items == [
        ("default_realm", "DOM1.SINK.TEST"),
        ("dns_lookup_kdc", "false"),
    ]
    assert kf.sections["domain_realm"].items == [
        (".dom1.sink.test", "DOM1.SINK.TEST")
    ]


def test_parse_nested_and_duplicates():
    kf = _load(krb5_main)
    key, group = kf.sections["realms"].items[0]
    assert key == "DOM1.SINK.TEST"
    assert isinstance(group, sambacc.krbconf.Group)
    assert group.items[0] == ("kdc", "kdc1.dom1.sink.test")
    assert group.items[1] == ("kdc", "kdc2.dom1.sink.test")
    assert group.items[2] == (
        "v4_name_convert",
        sambacc.krbconf.Group(
            [("host", sambacc.krbconf.Group([("rcmd", "host")]))]
        ),
    )


def test_repeated_section_is_merged():
    kf = _load("[a]\nx = 1\n[b]\ny = 2\n[a]\nz = 3\n")
    assert list(kf.sections) == ["a", "b"]
    assert kf.sections["a"].items == [("x", "1"), ("z", "3")]


def test_group_get_and_get_all():
    kf = _load(krb5_main)
    realm = kf.sections["realms"].get("DOM1.SINK.TEST")
    assert isinstance(realm, sambacc.krbconf.Group)
    # get returns a single value; with duplicates the last one wins
    assert realm.get("kdc") == "kdc2.dom1.sink.test"
    assert realm.get("nope") is None
    assert realm.get("nope", "foobar") == "foobar"
    assert realm.get_all("kdc") == [
        ("kdc", "kdc1.dom1.sink.test"),
        ("kdc", "kdc2.dom1.sink.test"),
    ]
    assert realm.get_all("nope") == []


def test_group_iter_and_eq():
    g = sambacc.krbconf.Group([("a", "b"), ("c", "d")])
    assert list(g) == [("a", "b"), ("c", "d")]
    assert g == sambacc.krbconf.Group([("a", "b"), ("c", "d")])
    assert g != sambacc.krbconf.Group.empty()
    assert g != [("a", "b"), ("c", "d")]


def test_directives_recorded():
    kf = _load("include /foo\n[libdefaults]\nincludedir /bar\n a = b\n")
    assert kf.directives == {
        1: ("include", "/foo"),
        3: ("includedir", "/bar"),
    }
    assert kf.sections == {"libdefaults": sambacc.krbconf.Group([("a", "b")])}


@pytest.mark.parametrize(
    "text",
    [
        "a = b\n",
        "[libdefaults]\n}\n",
        "[realms]\nX = {\n a = b\n",
        "[libdefaults]\nnot a relation\n",
        "[realms]\nX = {\n include /foo\n}\n",
    ],
)
def test_parse_errors(text):
    with pytest.raises(sambacc.krbconf.KrbConfError):
        _load(text)


def test_parse_error_reports_location():
    with pytest.raises(sambacc.krbconf.KrbConfError, match=r"test:3: "):
        _load("[libdefaults]\na = b\nnot a relation\n")


def test_dumplines():
    kf = _load(krb5_main.replace("includedir /etc/krb5.conf.d/\n", ""))
    lines = list(kf.dumplines())
    assert all(ln.endswith("\n") for ln in lines)
    assert "".join(lines) == (
        "[libdefaults]\n"
        "    default_realm = DOM1.SINK.TEST\n"
        "    dns_lookup_kdc = false\n"
        "\n"
        "[realms]\n"
        "    DOM1.SINK.TEST = {\n"
        "        kdc = kdc1.dom1.sink.test\n"
        "        kdc = kdc2.dom1.sink.test\n"
        "        v4_name_convert = {\n"
        "            host = {\n"
        "                rcmd = host\n"
        "            }\n"
        "        }\n"
        "    }\n"
        "\n"
        "[domain_realm]\n"
        "    .dom1.sink.test = DOM1.SINK.TEST\n"
        "\n"
    )


def test_writefp_output_has_one_item_per_line():
    kf = _load("[libdefaults]\na = b\nc = d\n[realms]\nX = {\nkdc = k\n}\n")
    fh = io.StringIO()
    kf.writefp(fh)
    lines = fh.getvalue().splitlines()
    assert "[libdefaults]" in lines
    assert [ln.strip() for ln in lines if ln.strip()] == [
        "[libdefaults]",
        "a = b",
        "c = d",
        "[realms]",
        "X = {",
        "kdc = k",
        "}",
    ]


def test_write_read_roundtrip(tmp_path):
    kf = _load(krb5_main.replace("includedir /etc/krb5.conf.d/\n", ""))
    out = tmp_path / "out.conf"
    kf.write(str(out))
    kf2 = sambacc.krbconf.KrbConfLoader(str(out))
    kf2.read()
    assert kf2.sections == kf.sections
    assert list(kf2.sections) == list(kf.sections)


def test_dumplines_with_directives_fails():
    kf = _load("include /foo\n[libdefaults]\na = b\n")
    with pytest.raises(sambacc.krbconf.KrbConfError):
        list(kf.dumplines())


def test_conf_dir_files(tmp_path):
    for name in ["b.conf", "a.conf", "plain-name_1", "x.rpmsave", "y.conf~"]:
        (tmp_path / name).write_text("")
    (tmp_path / "subdir.conf").mkdir()
    found = sambacc.krbconf.conf_dir_files(tmp_path)
    assert found == [
        tmp_path / "a.conf",
        tmp_path / "b.conf",
        tmp_path / "plain-name_1",
    ]


def test_conf_dir_files_missing(tmp_path):
    assert sambacc.krbconf.conf_dir_files(tmp_path / "nope") == []


def test_default_krb5_conf():
    assert sambacc.krbconf.default_krb5_conf() == pathlib.Path(
        "/etc/krb5.conf"
    )


def test_load(tmp_path):
    main, extra = _write_confs(tmp_path)
    conf = sambacc.krbconf.load([main, extra])
    assert list(conf.sources) == [main, extra]
    assert conf[main].sections["libdefaults"].get("default_realm") == (
        "DOM1.SINK.TEST"
    )
    assert conf[str(extra)].sections["libdefaults"].items == [
        ("forwardable", "true")
    ]


def test_load_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        sambacc.krbconf.load([tmp_path / "krb5.conf"])


def test_load_ignore_missing(tmp_path):
    main, _ = _write_confs(tmp_path)
    conf = sambacc.krbconf.load(
        [tmp_path / "nope.conf", main], ignore_missing=True
    )
    assert list(conf.sources) == [main]


def test_merged(tmp_path):
    main, extra = _write_confs(tmp_path)
    merged = sambacc.krbconf.load([main, extra]).merged()
    assert list(merged.sections) == ["libdefaults", "realms", "domain_realm"]
    assert merged.sections["libdefaults"].items[-1] == ("forwardable", "true")
    assert [k for k, _ in merged.sections["realms"]] == [
        "DOM1.SINK.TEST",
        "OTHER.ORG",
    ]
    assert merged.directives == {2: ("includedir", "/etc/krb5.conf.d/")}


def test_merged_does_not_modify_sources(tmp_path):
    main, extra = _write_confs(tmp_path)
    conf = sambacc.krbconf.load([main, extra])
    conf.merged()
    assert len(conf[main].sections["libdefaults"].items) == 2
    assert len(conf[extra].sections["libdefaults"].items) == 1


def test_parse_permitted_enctypes():
    kf = _load(krb5_enctypes)
    assert list(kf.sections) == ["libdefaults"]
    # the whole space separated list is a single value
    assert kf.sections["libdefaults"].items == [
        (
            "permitted_enctypes",
            "aes256-cts-hmac-sha384-192 aes128-cts-hmac-sha256-128",
        )
    ]


def test_permitted_enctypes_from_conf_dir_file(tmp_path):
    confs = _write_confs(tmp_path, crypto_policies=True)
    conf = sambacc.krbconf.load(confs)
    assert set(p.name for p in conf.sources) == {
        "crypto-policies",
        "extra.conf",
        "krb5.conf",
    }
    libdefaults = conf.merged().sections["libdefaults"]
    assert libdefaults.get("permitted_enctypes") == (
        "aes256-cts-hmac-sha384-192 aes128-cts-hmac-sha256-128"
    )
    # other libdefaults from the other files are still present
    assert libdefaults.get("default_realm") == "DOM1.SINK.TEST"
    assert libdefaults.get("forwardable") == "true"


def _snapshot(tmp_path):
    return {
        p: p.read_text() for p in sorted(tmp_path.rglob("*")) if p.is_file()
    }


def test_ensure_krb5_ad_algos_updates_crypto_policies(tmp_path):
    confs = _write_confs(tmp_path, crypto_policies=True)
    before = _snapshot(tmp_path)
    cpol = tmp_path / "krb5.conf.d/crypto-policies"

    sambacc.krbconf.ensure_krb5_ad_algos(confs)

    after = _snapshot(tmp_path)
    assert after.pop(cpol) == (
        "[libdefaults]\n"
        "    permitted_enctypes = aes256-cts-hmac-sha384-192"
        " aes128-cts-hmac-sha256-128"
        " aes256-cts-hmac-sha1-96 aes128-cts-hmac-sha1-96\n"
        "\n"
    )
    # no other files were touched
    del before[cpol]
    assert after == before

    # running again finds nothing more to do
    updated = cpol.read_text()
    sambacc.krbconf.ensure_krb5_ad_algos(confs)
    assert cpol.read_text() == updated


def test_ensure_krb5_ad_algos_skips(tmp_path, caplog):
    caplog.set_level("DEBUG", logger="sambacc.krbconf")
    main = tmp_path / "krb5.conf"
    cdir = tmp_path / "krb5.conf.d"
    cdir.mkdir()
    extra = cdir / "extra.conf"
    cpol = cdir / "crypto-policies"
    sources = [main, extra, cpol]
    all_algs = (
        "aes256-cts-hmac-sha1-96 aes128-cts-hmac-sha1-96"
        " aes256-cts-hmac-sha384-192"
    )

    def _check(expected_msg):
        before = _snapshot(tmp_path)
        caplog.clear()
        sambacc.krbconf.ensure_krb5_ad_algos(sources)
        assert expected_msg in caplog.text
        assert _snapshot(tmp_path) == before

    # no krb5.conf at all
    _check("no krb5.conf found")

    # krb5.conf without an includedir
    main.write_text("[libdefaults]\n    default_realm = DOM1.SINK.TEST\n")
    _check("no krb5.conf includedir found")

    # includedir present, but nothing in libdefaults
    main.write_text(
        "includedir /etc/krb5.conf.d\n[realms]\n    A = {\n    }\n"
    )
    _check("no libdefaults section found")

    # libdefaults present, but no permitted_enctypes
    main.write_text(
        "includedir /etc/krb5.conf.d/\n"
        "[libdefaults]\n"
        "    default_realm = DOM1.SINK.TEST\n"
    )
    _check("no permitted_enctypes key found")

    # permitted_enctypes present, but no crypto-policies file
    extra.write_text(
        "[libdefaults]\npermitted_enctypes = aes256-cts-hmac-sha384-192\n"
    )
    _check("no crypto-policies file found")

    # crypto-policies present and already has the needed algorithms
    cpol.write_text(f"[libdefaults]\npermitted_enctypes = {all_algs}\n")
    _check("ad support algorithms found")
