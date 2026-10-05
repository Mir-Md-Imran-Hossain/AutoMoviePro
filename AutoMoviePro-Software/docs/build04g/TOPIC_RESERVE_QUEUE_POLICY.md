# TOPIC RESERVE QUEUE POLICY (BUILD-04G)

**ভাষা:** বাংলা

## আলাদা রিজার্ভ

- `long_topic_reserve.json`
- `short_topic_reserve.json`

## ন্যূনতম

- প্রতি active format-এ **৫টি** valid topic (DEFAULT_RESERVE_MIN)
- কম হলে discovery trigger — **fake filler তৈরি নিষিদ্ধ**

## Queue order

- rank 1 = পরবর্তী topic
- consume হলে rank 2 promote

## Integrity

Reserve-এ duplicate, blocked, expired, invalid topic থাকতে পারে না — `repair_reserve()` self-repair করে।
