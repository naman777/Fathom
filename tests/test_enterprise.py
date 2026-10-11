from enterprise import acl, chunking


def test_gmail_list_literal_is_unpacked_into_emails():
    raw = "['From: a@x.com\\nSubject: Hi\\n\\nFirst body.', 'From: b@y.com\\n\\nSecond body.']"
    text = chunking.normalize("gmail", raw)
    assert "\\n" not in text and text.startswith("From: a@x.com\nSubject: Hi") and "Second body." in text


def test_escaped_newlines_are_repaired_only_when_they_dominate():
    assert chunking.normalize("confluence", "Overview:\\nLine two\\nLine three") == "Overview:\nLine two\nLine three"
    code = "real line\nreal line\nprint('a\\nb')\nreal line\nreal line"
    assert chunking.normalize("github", code) == code


def test_header_marks_real_slack_channels_only():
    assert chunking.header("slack", "eng-oncall") == "[Slack | #eng-oncall]"
    assert chunking.header("slack", "1987654321") == "[Slack | 1987654321]"
    assert chunking.header("jira", "") == "[Jira]"


def test_chunks_keep_messages_whole_and_carry_a_header():
    msgs = [f"user{i}: " + "word " * 40 for i in range(12)]  # about 205 characters each
    out = chunking.chunk("slack", "incidents", "\n\n".join(msgs), target=700, overlap=250)
    assert len(out) > 1 and all(c.startswith("[Slack | #incidents]\n") for c in out)
    assert all(len(c) <= 700 + 40 for c in out)
    body = [c.split("\n", 1)[1].split("\n\n") for c in out]
    assert all(m.strip() in [x.strip() for x in msgs] for b in body for m in b)  # no message was cut
    assert body[1][0] == body[0][-1]  # one message of overlap
    assert {m.strip() for b in body for m in b} == {m.strip() for m in msgs}  # nothing lost


def test_oversized_unit_is_split():
    out = chunking.chunk("confluence", "Doc", "A sentence here. " * 200, target=500)
    assert len(out) > 5 and all(len(c) <= 560 for c in out)


def test_empty_content_still_indexes_the_title():
    assert chunking.chunk("hubspot", "Acme Corp", "") == ["[HubSpot | Acme Corp]"]
    assert chunking.chunk("hubspot", "", "") == []


def test_groups_and_deny_by_default():
    assert acl.groups_for("slack", "people-ops") == ["people"]
    assert acl.groups_for("slack", "1987654321") == ["restricted"]
    assert acl.groups_for("some_new_source", "x") == ["restricted"]
    assert acl.groups_for("github", "anything") == ["eng"]


def test_roles():
    assert acl.can_read("engineer", ["eng"]) and not acl.can_read("engineer", ["people"])
    assert acl.can_read("hr", ["people"]) and not acl.can_read("hr", ["gtm"])
    assert acl.can_read("admin", ["restricted"]) and not acl.can_read("sales", ["restricted"])
    assert acl.role_groups("no-such-role") == ["all"] and acl.role_groups(None) == ["all"]  # least access, not most
    assert all(set(g or []) <= set(acl.GROUPS) for _, g in acl.ROLES.values())
