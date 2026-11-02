# Label and video snapshots

`bulk/labels.jsonl` contains 300 provisional video-level labels; `claim_level/labels.jsonl`
contains 10 separate claim-level pilot records. These are snapshots of the local
consolidated outputs, not human-verified ground truth. The 14 audited claim aggregates
in the bulk set and 286 provisional screens have different methods; use the `label_tier`
field when analyzing them. See the collection and labeling documentation for details.

`videos/` contains 300 MP4 files tracked with Git LFS, named by `video_key`. Their
SHA-256 hashes were checked against the bulk labels. Install Git LFS and run
`git lfs pull` after cloning to retrieve the media. Source URLs and hashes are in
the bulk labels. These are third-party videos; availability does not establish
redistribution rights, so review their terms and rights before reuse.

The working output under `data/` remains ignored. Update these snapshots deliberately
when new labels or media are ready; changing the working files does not update them.
