from types import SimpleNamespace
import testbot as sut


def test_format_path():
    assert sut.format_path(path="11d7") == "11,d7"
    assert sut.format_path(path="11d7", path_hash_size=1) == "11,d7"
    assert sut.format_path(path="11d7", path_hash_size=2) == "11d7"
    assert sut.format_path(path="11d7aa4388a3", path_hash_size=1) == "11,d7,aa,43,88,a3"
    assert sut.format_path(path="11d7aa4388a3", path_hash_size=2) == "11d7,aa43,88a3"
    assert sut.format_path(path="11d7aa4388a3", path_hash_size=3) == "11d7aa,4388a3"
    assert sut.format_path("11d7aa4388a3", 3) == "11d7aa,4388a3"


def test_decrypt_message():
    payload = "150211d7354845b517f10657ccdb4f05582892d9a229f66149d5e35b53c795e47a934b2f928d880c7d3f6967502179c9d3005e157f7e69c51ebcbc5e9f853d7afdbf0d9f8134ab4a4e6c01bcc02efb618cf582c97056b7ffd68ce1fcbade6ffd3bc9b7c7e11ba3"
    assert sut.decrypt_message(payload) == {
        "flags": 0,
        "message": "@[rotaliator🚲]pong | hops=1 | bytes/hop=None | path=unknown",
        "sender": "Bot Puławy🏭",
        "timestamp": 1779820086,
    }


def test_format_response():
    text = "test 123"
    sender = "Janusz"
    hops = 2
    path_hash_size = 1
    path = "11d7"
    assert (
        sut.format_response(text, sender, hops, path_hash_size, path)
        == "@[Janusz]re: test 123 | hops=2 | bytes/hop=1 | path=11,d7"
    )
    text = "123456789012345678901"
    assert (
        sut.format_response(text, sender, hops, path_hash_size, path)
        == "@[Janusz]re: 12345678901234567... | hops=2 | bytes/hop=1 | path=11,d7"
    )
    text = "Test ze spacją "
    assert (
        sut.format_response(text, sender, hops, path_hash_size, path)
        == "@[Janusz]re: Test ze spacją | hops=2 | bytes/hop=1 | path=11,d7"
    )


def test_prepare_response():
    events = [
        SimpleNamespace(
            payload={
                "chan_name": "#bot-test",
                "path": "",
                "path_hash_size": 2,
                "path_len": 0,
                "payload": "15403543d4d411182578e3380795a6f69f98a28178c7b91e5760b3657eca603e1132130af8",
                "pkt_hash": 3681665355,
            },
        ),
        SimpleNamespace(
            payload={
                "chan_name": "#bot-test",
                "path": "11ab",
                "path_hash_size": 2,
                "path_len": 1,
                "payload": "154111ab3543d4d411182578e3380795a6f69f98a28178c7b91e5760b3657eca603e1132130af8",
                "pkt_hash": 3681665355,
            },
        ),
        SimpleNamespace(
            payload={
                "chan_name": "#bot-test",
                "path": "d7c7",
                "path_hash_size": 2,
                "path_len": 1,
                "payload": "1541d7c73543d4d411182578e3380795a6f69f98a28178c7b91e5760b3657eca603e1132130af8",
                "pkt_hash": 3681665355,
            }
        ),
    ]
    response = sut.prepare_response(events)
    assert (
        response
        == "@[rotaliator🚲]re: Test again | bytes=2 | path1=direct; path2=11ab; path3=d7c7"
    )


def test_split_message():
    short_message = "@[rotaliator🚲]re: Test again | bytes=2 | path1=direct; path2=11ab; path3=d7c7"
    splitted_message = sut.split_message(short_message, max_length=100)
    assert splitted_message == [short_message]


    splitted_message = sut.split_message(short_message, max_length=50)
    assert splitted_message == [
        "1/2 @[rotaliator🚲]re: Test again | bytes=2 |",
        "2/2 path1=direct; path2=11ab; path3=d7c7",
    ]

    long_message = "@[rotaliator🚲]re: Test again | bytes=2 | path1=direct; path2=11ab00,ababab,123456; path3=d7c700,ababab,123456"
    splitted_message = sut.split_message(long_message, max_length=100)
    assert splitted_message == [
        "1/2 @[rotaliator🚲]re: Test again | bytes=2 | path1=direct; path2=11ab00,ababab,123456; path3=d7c700,",
        "2/2 ababab,123456",
    ]


test_path_events1 = [
        SimpleNamespace(
            payload={'path': '7a9b8d028b009c3d2d8c8cf2435dd7c7',
                     'path_hash_size': 2},
        ),
        SimpleNamespace(
            payload={'path': '7a9b8d028b009c3d2d8c8cf2435dd7c711ab',
                     'path_hash_size': 2}
        ),
        SimpleNamespace(
            payload={'path': '7a9b8d028b009c3d2d8c8cf2435dd7c7aaf5',
                     'path_hash_size': 2}
        ),
]

test_path_events2 = [
        SimpleNamespace(
            payload={'path': '7a9b8d028b00',
                     'path_hash_size': 2},
        ),
        SimpleNamespace(
            payload={'path': '7a9b8d028b009c3d2d8c8cf2435dd7c7',
                     'path_hash_size': 2}
        ),
        SimpleNamespace(
            payload={'path': '7a9b8d028b009c3d2d8c8cf2435dd7c7aaf5',
                     'path_hash_size': 2}
        ),
]

def test_format_paths():
    paths = sut.format_paths(test_path_events1, 2)
    assert paths == [
        "path1=7a9b,8d02,8b00,9c3d,2d8c,8cf2,435d,d7c7",
        "path2=7a9b,8d02,8b00,9c3d,2d8c,8cf2,435d,d7c7,11ab",
        "path3=7a9b,8d02,8b00,9c3d,2d8c,8cf2,435d,d7c7,aaf5",
    ]

def test_format_paths_compact():
    paths = sut.format_paths_compact(test_path_events1, 2)
    assert paths == [
        "path1=7a9b,8d02,8b00,9c3d,2d8c,8cf2,435d,d7c7",
        "path2=path1+11ab",
        "path3=path1+aaf5",
    ]
    paths = sut.format_paths_compact(test_path_events2, 2)
    assert paths == [
        "path1=7a9b,8d02,8b00",
        "path2=path1+9c3d,2d8c,8cf2,435d,d7c7",
        "path3=path2+aaf5",
    ]
