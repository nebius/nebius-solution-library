# OpenFold2 regional new-node benchmark result

Run `of2-newnode-r5-regional` completed with the frozen semantic receipt,
lifecycle receipt, and cleanup receipt all at `PASS`. The true demand edge was
the exact node-group `0 -> 1` request at
`2026-08-18T05:31:25.603010500Z`.

| Phase from demand | Seconds |
| --- | ---: |
| Strict new-node admission | 106.373 |
| CRIU agent Ready | 107.099 |
| Target created/scheduled | 119.397 |
| Placeholder process start | 522.397 |
| HTTP Ready | 573.397 |
| Native restore receipt | 573.481 |
| Two strict semantic responses | **575.459** |
| Benchmark PASS recorded | 590.520 |
| Full cleanup and holder restoration | 774.171 |

The exact 10,698,531,042-byte regional image took **260.653 seconds** to
cold-pull. That is 9.559 seconds, or 3.81%, slower than the 251.094-second NGC
pull in r4. The byte-identical regional mirror is therefore not a cold-load
optimization on the current node/registry path.

The full demand-to-two-response result nevertheless improved from 607.247235
seconds to 575.458978 seconds: **31.788257 seconds (5.23%) lower**. The new node
admitted 12.681 seconds sooner, the settled harness avoided r4's in-clock manual
seccomp recovery, and storage-control-plane timings differed. Native restore was
effectively unchanged (4.131 seconds versus 4.083 seconds), so none of this
delta should be attributed to the regional registry.

Both strict 20-residue folds passed through the run-scoped ClusterIP and
separate CPU probe in 1.888578 and 0.958277 seconds. Cleanup restored the node
group to `1/1/1/1`, removed all run-scoped resources, recreated the holder Ready
on t12, and confirmed both RWO volumes attached there.

Raw evidence:

`<private-evidence-root>/openfold2-newnode-production-20260818/runs/of2-newnode-r5-regional/`
