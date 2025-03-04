# Problem 

Large Language Model - GPT3 175B

# Quality

| Quality metric |    Quality target |         Evaluation frequency         |              Evaluation thoroughness              |
|:---------------|------------------:|:------------------------------------:|:-------------------------------------------------:|
| Log Perplexity |              2.69 | Every 24576 samples (=50.33B tokens) | Validation subset that consists of 24567 examples |

# Running benchmark

## Hyperparameter settings

Launch configuration and system-specific hyperparameters for the appropriate
NVIDIA DGX submission are in the `config_*.sh` scripts.

You can choose particular config to be executed via `-c <path>` option.
If not passed, it would be automatically resolved with the following variables:
- GPU type
- Worker count

You can create your own config based on following.

Naming convention for config file names:
```shell
"config_${GPU_TYPE}x${NUMBER_OF_GPUS_PER_NODE}_NODEx${NUMBER_OF_NODES}_TPx${TENSOR_PARALLELISM}_PPx${PIPELINE_PARALLELISM}_VPx${INTERLEAVED_PIPELINE}_MINBSx${MINI_BATCH_SIZE}_MICBSx${MICRO_BATCH_SIZE}`"
```

There are following conventions used for hyperparameters:

```
MP = TP * PP
DP = WS // MP
miniBS = GBS // DP
```

where: 

```
MP = model parallelism
TP = tensor parallelism
PP = pipeline parallelism
DP = data parallelism
WS = world size (number of nodes x number of gpus per node)
GBS = global batch size
```

> [!NOTE]
> Changing `MICRO_BATCH_SIZE` doesn't affect GBS or any of the above parameters.
> Effectively it controls gradient accumulation (`GA = miniBS // microBS`).

Additional requirement for every config is that the GBS should be divisible by `DP*PP*MICRO_BATCH_SIZE`

### Metric exporting to MLFlow

If MLFlow logger is used for metric exporting, you can compare benchmark runs based on metrics.

#### How to interpret metrics?

For metrics having statistics:

- `mean` - average value across metric values.
- `median` - the middle value across sorted metric values.
- `p75` - 3/4 rd value across sorted metric values.
- `std` - standard deviation - how far outliers lay in origin to the mean of metric values.

It’s convenient to look at:
- `median` or `p75` - to eliminate outliers income into the metric value and see how performant the run is.
- `std` - to see if the run is smooth and stable - lower values mean better stability.

##### Duration

_All time metrics are in seconds._

- `timeToRun` - time between running python script from [run_and_time.sh](./run_and_time.sh) to `on_fit_start` callback call.

  Usually means time needed to run Python runtime and to prepare framework.

- `initialization` - time from `fit_start` to `train_start`.

  Usually means dataset loading time.

- `training_step` - time from train_batch_start to train_batch_end.

  Usually means how performant the run is.

- `validation_step` - time from validation_bath_start to validation_batch_end.

  Usually means how performant the run is.

- `warmup_` `cudagraph`/`training`/`validation` - time taken for warming data loader and model up.

##### Samples per second

- `training_step` - number of samples consumed during training step.

  Usually means how performant the run is.

- `validation_step` - number of samples consumed during validation step.

  Usually means how performant the run is.

## Starting a job

To start a job, follow the [instructions](../README.md).
