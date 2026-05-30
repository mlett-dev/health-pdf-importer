---
name: anytype
description: Use the configured Anytype MCP servers for searching, reading, and updating Anytype spaces and objects. Prefer MCP over browser automation, and prefer compact extension tools when available.
---

# Anytype Via MCP

Use this skill whenever the user asks to search, read, create, update, organize, or analyze data in Anytype.

The environment may expose two Anytype MCP servers:

- Official Anytype MCP: canonical tools for full Anytype API behavior.
- Anytype extension MCP: sidecar tools for file operations and compact REST wrappers.

## Tool Priority

Default rule: use compact extension tools first when a compact tool exists. Use the official tool only when you need fields that the compact tool omits, when the compact tool fails, or when there is no compact equivalent.

Prefer these compact tools:

- `search-global-compact` instead of official global search for discovery.
- `search-space-compact` instead of official space search when a `space_id` is known.
- `list-objects-compact` instead of official `list-objects`.
- `get-list-objects-compact` instead of official `get-list-objects`.
- `get-object-compact` instead of official `get-object` for normal inspection.
- `get-objects-compact-many` instead of many repeated `get-object-compact` calls.
- `update-object-compact` instead of official `update-object` when the update response only needs confirmation or a small object summary.
- `update-objects-compact-many` when updating several objects in the same space.
- `create-objects-compact-many` when creating several objects in the same space.
- `list-types-compact` instead of official `list-types`.
- `get-type-compact` instead of official `get-type` for normal schema inspection.
- `get-list-views-compact` instead of official `get-list-views` unless full filters and sorts are required.

Use official tools for:

- single create operations when creating exactly one object; there is no `create-object-compact` tool.
- delete, move, archive, or bulk operations when only official tools support them.
- full object bodies, full property payloads, full type definitions, or complete list view filters/sorts.
- debugging mismatches between compact output and official API output.

## Compact Tool Defaults

Keep compact calls small:

- Use `limit` and `offset`; start with `limit: 20` to `50`.
- Do not request properties by default.
- If properties are needed, pass `property_keys` for the exact properties needed. `property_keys` accepts technical keys, property IDs, or visible property names. Prefer technical keys after schema inspection.
- `property_keys` automatically enables property output. You do not also need `include_properties: true` when `property_keys` is present.
- Use `include_properties: true` only when you want properties but do not know exact keys yet. This returns at most `max_properties`.
- Use `include_type`, `include_icon`, `include_filters`, and `include_sorts` only when needed.
- Keep `max_string_length` at the default unless the user asks for full text.

If compact output is not enough, make one follow-up official call for the exact object, type, view, or list that needs full detail.

For `*-many` tools, response-shaping options such as `fields`, `property_keys`, `include_properties`, `include_type`, `include_icon`, `max_properties`, and `max_string_length` are top-level tool arguments. They apply to every returned object. Do not place these options inside `items`.

## `fields` vs `property_keys`

These two parameters are different. Do not mix them up.

- `fields` selects top-level object fields.
- `property_keys` selects entries inside the object's `properties`.
- `fields` values are names like `id`, `name`, `snippet`, `layout`, `archived`, `space_id`, `object`, `type`, `icon`, `properties`, `markdown`.
- `property_keys` values are Anytype property keys, property IDs, or visible property names like `status`, `due_date`, `69dfc55ae30a1bc568a59c05`, `Status`, `Due Date`.
- Do not put property names in `fields`. Wrong: `"fields": ["id", "name", "Status"]`.
- Do not put top-level fields in `property_keys`. Wrong: `"property_keys": ["id", "name"]`.

Good examples:

```json
{
  "space_id": "SPACE_ID",
  "object_id": "OBJECT_ID",
  "fields": ["id", "name"],
  "property_keys": ["status", "due_date"]
}
```

This means: return only top-level `id` and `name`, plus the two selected properties `status` and `due_date`.

```json
{
  "space_id": "SPACE_ID",
  "object_id": "OBJECT_ID",
  "fields": ["id", "name", "snippet"],
  "include_properties": false
}
```

This means: return no properties, only top-level summary fields.

```json
{
  "space_id": "SPACE_ID",
  "object_id": "OBJECT_ID",
  "fields": ["id", "name", "properties"],
  "max_properties": 5
}
```

This means: include top-level `id` and `name`, and include up to 5 properties because `fields` contains `properties`. Prefer exact `property_keys` when possible.

## Many Tools

Use `*-many` tools when doing the same operation for several objects in the same space. This avoids long transcripts with repeated tool calls.

Naming rule:

- Single object: `get-object-compact`, `update-object-compact`.
- Many objects: `get-objects-compact-many`, `update-objects-compact-many`, `create-objects-compact-many`.
- File tools use the same suffix style: `file-upload-many`, `file-download-many`.

### `get-objects-compact-many`

Use this after search/list results when you have multiple object IDs and need the same fields/properties from all of them.

Required:

- `space_id`
- `object_ids`: array of object IDs

Optional:

- `format`: use `"md"` only when markdown body is needed.
- `fields`, `property_keys`, `include_type`, `include_icon`, `max_properties`, `max_string_length`: shared compact output options for every object.
- `stop_on_error`: default `false`. Keep `false` unless the next result depends on every object succeeding.

Example:

```json
{
  "space_id": "SPACE_ID",
  "object_ids": ["OBJ_1", "OBJ_2", "OBJ_3"],
  "fields": ["id", "name"],
  "property_keys": ["status", "due_date"],
  "stop_on_error": false
}
```

### `update-objects-compact-many`

Use this when changing several existing objects in the same space. Inspect first, then send the smallest update payload.

Required:

- `space_id`
- `items`: array of update objects
- each item requires `object_id`
- each item must include at least one update field: `name`, `markdown`, `properties`, `icon`, or `type_key`

Compact output options (`fields`, `property_keys`, etc.) are top-level parameters and apply to every returned object. Do not place compact options inside each item.

Example:

```json
{
  "space_id": "SPACE_ID",
  "items": [
    {"object_id": "OBJ_1", "name": "Invoice 001"},
    {"object_id": "OBJ_2", "name": "Invoice 002"}
  ],
  "fields": ["id", "name"],
  "stop_on_error": false
}
```

Example with properties:

```json
{
  "space_id": "SPACE_ID",
  "items": [
    {
      "object_id": "OBJ_1",
      "properties": [
        {"key": "status", "select": "done"}
      ]
    },
    {
      "object_id": "OBJ_2",
      "properties": [
        {"key": "status", "select": "done"}
      ]
    }
  ],
  "fields": ["id", "name"],
  "property_keys": ["status"]
}
```

## Property Update Payloads

Anytype property updates are typed property-link values. Do not send generic `value` fields for updates unless the official API docs explicitly require it for that endpoint. Do not send `null` as a property value.

Wrong:

```json
{
  "properties": [
    {"key": "anhange", "value": null},
    {"key": "69dfc55ae30a1bc568a59c09", "value": ["OBJECT_ID"]}
  ]
}
```

This fails with `could not determine property link value type` because Anytype cannot infer whether `value: null` means text, files, objects, select, date, or another format.

Use exactly one typed value field per property item:

- Text: `{"key": "description", "text": "Some text"}`
- Number: `{"key": "amount", "number": 42}`
- Select: `{"key": "status", "select": "done"}`
- Multi-select: `{"key": "tags", "multi_select": ["important"]}`
- Date: `{"key": "due_date", "date": "2026-04-27"}`
- Files/attachments: `{"key": "attachments", "files": ["FILE_OBJECT_ID"]}`
- Object/relation links: `{"key": "related", "objects": ["OBJECT_ID"]}`
- Checkbox: `{"key": "done", "checkbox": true}`
- URL/email/phone: `url`, `email`, or `phone`

To clear a property, use a typed empty value that matches the property format:

- `files: []` for file/attachment properties.
- `objects: []` for object/relation properties.
- `multi_select: []` for multi-select properties.
- `text: ""`, `url: ""`, `email: ""`, or `phone: ""` for string-like properties if clearing is intended.
- `checkbox: false` for checkboxes.

Before updating an unfamiliar property, inspect the object type with `get-type-compact` and include the relevant property definition. Prefer the technical property `key` from the type schema over the visible name. If a property looks like an attachment or relation, use `files` or `objects`; do not guess with `value`.

### `create-objects-compact-many`

Use this when creating several objects in the same space. Search first to avoid duplicates.

Required:

- `space_id`
- `items`: array of create objects
- each item requires `type_key`

Optional per item:

- `name`
- `body`: initial markdown-capable body for create
- `properties`
- `icon`
- `template_id`

Important: create uses `body`; update uses `markdown`.

Compact output options (`fields`, `property_keys`, etc.) are top-level parameters and apply to every returned object.

Example:

```json
{
  "space_id": "SPACE_ID",
  "items": [
    {"type_key": "page", "name": "Project A", "body": "Initial notes"},
    {"type_key": "page", "name": "Project B", "body": "Initial notes"}
  ],
  "fields": ["id", "name", "type"],
  "include_type": true,
  "stop_on_error": false
}
```

## File Tools

Use extension file tools for local file transfer:

- `file-info` to inspect configured roots.
- `file-list-input` before upload; reuse returned `relative_path` exactly.
- `file-upload` or `file-upload-many` for staged uploads.
- `file-download` or `file-download-many` for Anytype file objects.
- `file-list-output` to verify downloads.

Do not rewrite filenames. Preserve spaces, umlauts, and special characters exactly as returned by `file-list-input`.

## Safety Rules

- Prefer Anytype MCP tools over browser automation.
- Before creating anything, search first to avoid duplicates.
- Before changing schema-like things, inspect the existing space, types, properties, and lists first.
- Use only spaces that the bot account can already access.
- Treat deletes, moves, and bulk edits as destructive; do them only on explicit user intent.
- Do not guess type, property, space, list, or view IDs when they can be inspected.
- Do not create duplicates if a matching object already exists.
- Do not use browser clicks for normal Anytype work unless MCP is unavailable.

## Default Workflow

1. Find the correct space, preferably with compact search.
2. Search for existing matching objects.
3. If needed, inspect compact types, properties, lists, and views.
4. Use official tools only for missing detail or operations not covered by compact tools.
5. Apply the smallest safe change.
6. Report what changed, including the object/list/type names and IDs when useful.

## Common Patterns

- Find notes, tasks, or pages: use `search-space-compact` if the space is known; otherwise use `search-global-compact`.
- Inspect a collection or set: use `get-list-views-compact`, then `get-list-objects-compact`.
- Use `list-objects-compact` for broad object listing in one space; use `get-list-objects-compact` only when you have both `list_id` and `view_id`.
- `filters` on compact list/search tools are raw Anytype REST query parameters. They are not view filter definitions and not Notion-style filters.
- Inspect many objects from a list/search page: use `list-objects-compact` or `get-list-objects-compact` with a small `limit`.
- Inspect many known object IDs: use `get-objects-compact-many`, not repeated `get-object-compact`.
- Inspect one object deeply: try `get-object-compact` first, then official `get-object` only if full markdown or complete properties are required.
- Inspect schema: use `list-types-compact` and `get-type-compact`; ask for properties only by key when possible.
- Update an object: inspect first, update with the smallest payload, and prefer `update-object-compact` for the response.
- Update many objects: inspect first, then use `update-objects-compact-many` with one `items` entry per object.
- Create many objects: search first for duplicates, then use `create-objects-compact-many`.
