# Local work recovery checkpoint

Original checkouts and staging were left untouched. Each .snapshot file contains the exact bytes of its original path. manifest.json records the original base commit, path, file mode, state and SHA-256. Working and staged versions are separate; deletion records have no blob.

Recover individual files by copying the selected snapshot to its recorded original path and applying its recorded mode. Use the original base commit for a separate recovery worktree; do not blindly overlay older versions on current main. Local-only source commits retained as merge parents are also reachable from this branch.

This branch is a recovery checkpoint, not a merge-ready implementation or release. Excluded dependencies, generated intermediates, machine state and scanner findings remain in the original trees.
