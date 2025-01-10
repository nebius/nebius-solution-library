import os
from dataclasses import dataclass, field
from datetime import datetime as DateTime
from datetime import timedelta as TimeDelta
from enum import Enum
from typing import Any, Optional, Sequence

import mlflow.entities as mlf
import pandas as pd
from pytorch_lightning import Callback, LightningModule, Trainer
from pytorch_lightning.loggers import MLFlowLogger
from pytorch_lightning.utilities import rank_zero_only
from pytorch_lightning.utilities.types import STEP_OUTPUT

from custom_callbacks import compute_consumed_mllog_tokens


@dataclass
class BenchmarkParams:
    # fmt: off

    training_block_size:    int = 0
    training_block_samples: int = 0
    training_step_samples:  int = 0

    # fmt: on


class BenchmarkKeys(str, Enum):
    # fmt: off

    BENCHMARK               = 'benchmark'
    STAT_MEAN               = 'mean'
    STAT_STD                = 'std'
    STAT_MEDIAN             = 'median'
    STAT_PERC_75            = 'p75'

    PARAM_TRAINING_BLOCK_SIZE        = f'{BENCHMARK}/training/block/size'
    PARAM_TRAINING_BLOCK_SAMPLES     = f'{BENCHMARK}/training/block/samples'
    PARAM_TRAINING_STEP_SAMPLES      = f'{BENCHMARK}/training/step/samples'

    METRIC_DURATION_TIME_TO_RUN      = f'{BENCHMARK}/duration/timeToRun'
    METRIC_DURATION_TOTAL            = f'{BENCHMARK}/duration/total'
    METRIC_DURATION_INITIALIZATION   = f'{BENCHMARK}/duration/initialization'
    METRIC_DURATION_TRAINING         = f'{BENCHMARK}/duration/training'
    METRIC_DURATION_VALIDATION_BLOCK = f'{BENCHMARK}/duration/validation/block'

    METRIC_SAMPLES_PER_SECOND_TRAINING_EPOCH  = f'{BENCHMARK}/samplesPerSecond/training/epoch'
    METRIC_SAMPLES_PER_SECOND_TRAINING_BLOCK  = f'{BENCHMARK}/samplesPerSecond/training/block'
    METRIC_SAMPLES_PER_SECOND_TRAINING_STEP   = f'{BENCHMARK}/samplesPerSecond/training/step'
    METRIC_SAMPLES_PER_SECOND_VALIDATION_STEP = f'{BENCHMARK}/samplesPerSecond/validation/step'

    # fmt: on

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return self.value


@dataclass
class MetricKV:
    key: str
    value: float


@dataclass
class ParamKV:
    key: str
    value: str


@dataclass
class Statistics:
    last: float
    mean: float
    std: float
    median: float
    p75: float


@dataclass
class MetricMixin:
    metric_name: str


@dataclass
class StatisticsMixin(MetricMixin):
    _records: list[float] = field(default_factory=list)

    @property
    def statistics(self) -> Statistics:
        if len(self._records) == 0:
            return Statistics(
                last=0.0,
                mean=0.0,
                std=0.0,
                median=0.0,
                p75=0.0,
            )

        s = pd.Series(self._records, dtype=float)
        median, p75 = list(s.quantile([0.5, 0.75]))
        return Statistics(
            last=s.iloc[-1],
            mean=s.mean(),
            std=s.std(),
            median=median,
            p75=p75,
        )

    @property
    def stat_metrics(self) -> Sequence[MetricKV]:
        if len(self._records) == 0:
            return []

        statistics = self.statistics
        res = [
            MetricKV(
                key=self.metric_name,
                value=statistics.last,
            )
        ]

        for key in [
            BenchmarkKeys.STAT_MEAN.value,
            BenchmarkKeys.STAT_STD.value,
            BenchmarkKeys.STAT_MEDIAN.value,
            BenchmarkKeys.STAT_PERC_75.value,
        ]:
            res.append(
                MetricKV(
                    key=f'{self.metric_name}_{key}',
                    value=getattr(statistics, key),
                )
            )

        return res


@dataclass
class DurationMetric(StatisticsMixin):
    _initial_timestamp: DateTime = DateTime.now()
    _elapsed_time: TimeDelta = TimeDelta()

    def reset(self, initial_timestamp: DateTime) -> None:
        self._initial_timestamp = initial_timestamp
        self._elapsed_time = TimeDelta()

    def update(self, timestamp: DateTime) -> None:
        self._elapsed_time = timestamp - self._initial_timestamp

        self._records.append(self._elapsed_time.total_seconds())

    @property
    def elapsed_seconds(self) -> float:
        return self._elapsed_time.total_seconds()


@dataclass
class SamplesPerSecondMetric(StatisticsMixin):
    _timestamp_start: DateTime = DateTime.now()
    _timestamp_end: DateTime = DateTime.now()
    _consumed_samples_start: int = 0
    _consumed_samples_end: int = 0

    def start(self, timestamp: DateTime) -> None:
        self._timestamp_start = timestamp
        self._timestamp_end = timestamp
        self._consumed_samples_start = self._consumed_samples_end

    def stop(self, timestamp: DateTime, consumed_samples: int) -> None:
        self._timestamp_end = timestamp
        self._consumed_samples_end = consumed_samples

        samples_per_block = self._consumed_samples_end - self._consumed_samples_start
        duration = self._timestamp_end - self._timestamp_start

        self._records.append(samples_per_block / duration.total_seconds())


@dataclass
class BenchmarkMetrics:
    # fmt: off

    time_to_run_duration      = DurationMetric(BenchmarkKeys.METRIC_DURATION_TIME_TO_RUN.value)
    total_duration            = DurationMetric(BenchmarkKeys.METRIC_DURATION_TOTAL.value)
    training_duration         = DurationMetric(BenchmarkKeys.METRIC_DURATION_TRAINING.value)
    initialization_duration   = DurationMetric(BenchmarkKeys.METRIC_DURATION_INITIALIZATION.value)
    validation_block_duration = DurationMetric(BenchmarkKeys.METRIC_DURATION_VALIDATION_BLOCK.value)

    training_epoch_samples_per_second  = SamplesPerSecondMetric(BenchmarkKeys.METRIC_SAMPLES_PER_SECOND_TRAINING_EPOCH.value)
    training_block_samples_per_second  = SamplesPerSecondMetric(BenchmarkKeys.METRIC_SAMPLES_PER_SECOND_TRAINING_BLOCK.value)
    training_step_samples_per_second   = SamplesPerSecondMetric(BenchmarkKeys.METRIC_SAMPLES_PER_SECOND_TRAINING_STEP.value)
    validation_step_samples_per_second = SamplesPerSecondMetric(BenchmarkKeys.METRIC_SAMPLES_PER_SECOND_VALIDATION_STEP.value)

    # fmt: on


class BenchmarkCallback(Callback):
    ENV_VAR_TIMING_START_TIME = 'MLF_VALUE_TIMING_START_TIME'

    def __init__(self, cfg):
        super().__init__()

        self.params: BenchmarkParams = BenchmarkParams(
            training_block_size=cfg.trainer.val_check_interval,
            training_block_samples=(
                cfg.trainer.val_check_interval * cfg.model.global_batch_size * cfg.model.encoder_seq_length
            ),
            training_step_samples=cfg.model.global_batch_size * cfg.model.encoder_seq_length,
        )
        self.metrics: BenchmarkMetrics = BenchmarkMetrics()

    @rank_zero_only
    def on_fit_start(self, trainer: Trainer, pl_module: LightningModule) -> None:
        now = DateTime.now()
        self.metrics.time_to_run_duration.reset(
            DateTime.fromtimestamp(int(os.environ.get(self.ENV_VAR_TIMING_START_TIME, default=int(now.timestamp()))))
        )
        self.metrics.total_duration.reset(now)
        self.metrics.initialization_duration.reset(now)

        self.log_metrics(
            trainer,
            [self._update_duration_metric(self.metrics.time_to_run_duration, now)],
            timestamp=now,
            params=[
                ParamKV(
                    key=BenchmarkKeys.PARAM_TRAINING_BLOCK_SIZE.value,
                    value=str(self.params.training_block_size),
                ),
                ParamKV(
                    key=BenchmarkKeys.PARAM_TRAINING_BLOCK_SAMPLES.value,
                    value=str(self.params.training_block_samples),
                ),
                ParamKV(
                    key=BenchmarkKeys.PARAM_TRAINING_STEP_SAMPLES.value,
                    value=str(self.params.training_step_samples),
                ),
            ],
        )

    @rank_zero_only
    def on_fit_end(self, trainer: Trainer, pl_module: LightningModule) -> None:
        now = DateTime.now()
        self.log_metrics(
            trainer,
            [self._update_duration_metric(self.metrics.total_duration, now)],
            timestamp=now,
        )

    @rank_zero_only
    def on_train_start(self, trainer: Trainer, pl_module: LightningModule) -> None:
        now = DateTime.now()
        self.metrics.training_duration.reset(now)
        self.log_metrics(
            trainer,
            metrics=[
                self._update_duration_metric(self.metrics.initialization_duration, now),
                self._update_duration_metric(self.metrics.training_duration, now),
            ],
            timestamp=now,
        )

    @rank_zero_only
    def on_train_end(self, trainer: Trainer, pl_module: LightningModule) -> None:
        now = DateTime.now()
        self.log_metrics(
            trainer,
            metrics=[
                self._update_duration_metric(self.metrics.training_duration, now),
            ],
            timestamp=now,
            with_duration_metrics=[self.metrics.total_duration],
        )

    @rank_zero_only
    def on_train_epoch_start(self, trainer: Trainer, pl_module: LightningModule) -> None:
        self.metrics.training_epoch_samples_per_second.start(DateTime.now())

    @rank_zero_only
    def on_train_epoch_end(self, trainer: Trainer, pl_module: LightningModule) -> None:
        now = DateTime.now()
        self.metrics.training_epoch_samples_per_second.stop(now, compute_consumed_mllog_tokens(trainer, pl_module))
        self.log_metrics(
            trainer,
            metrics=self.metrics.training_epoch_samples_per_second.stat_metrics,
            timestamp=now,
        )

    @rank_zero_only
    def on_train_batch_start(
        self,
        trainer: Trainer,
        pl_module: LightningModule,
        batch: Any,
        batch_idx: int,
    ) -> None:
        self.metrics.training_block_samples_per_second.start(DateTime.now())

    @rank_zero_only
    def on_train_batch_end(
        self,
        trainer: Trainer,
        pl_module: LightningModule,
        outputs: STEP_OUTPUT,
        batch: Any,
        batch_idx: int,
    ) -> None:
        now = DateTime.now()
        self.metrics.training_block_samples_per_second.stop(now, compute_consumed_mllog_tokens(trainer, pl_module))
        self.log_metrics(
            trainer,
            metrics=self.metrics.training_block_samples_per_second.stat_metrics,
            timestamp=now,
            with_duration_metrics=[
                self.metrics.total_duration,
                self.metrics.training_duration,
            ],
        )

    @rank_zero_only
    def on_validation_start(self, trainer: Trainer, pl_module: LightningModule) -> None:
        self.metrics.validation_block_duration.reset(DateTime.now())

    @rank_zero_only
    def on_validation_end(self, trainer: Trainer, pl_module: LightningModule) -> None:
        now = DateTime.now()
        self._update_duration_metric(self.metrics.validation_block_duration, now)
        self.log_metrics(
            trainer,
            metrics=self.metrics.validation_block_duration.stat_metrics,
            timestamp=now,
        )

    def log_metrics(
        self,
        trainer: Trainer,
        metrics: Sequence[MetricKV],
        timestamp: DateTime,
        params: Optional[Sequence[ParamKV]] = None,
        with_duration_metrics: Optional[Sequence[DurationMetric]] = None,
    ) -> None:
        logger = BenchmarkCallback._get_mlflow_logger(trainer)
        if logger is None:
            return

        if with_duration_metrics is not None:
            metrics = list(metrics) + [
                self._update_duration_metric(metric, timestamp) for metric in with_duration_metrics
            ]

        full_metrics = [
            mlf.Metric(
                key=metric.key,
                value=metric.value,
                timestamp=timestamp.microsecond // 1000,
                step=trainer.global_step,
            )
            for metric in metrics
        ]

        logger.experiment.log_batch(
            run_id=logger.run_id,
            metrics=full_metrics,
            params=([mlf.Param(key=param.key, value=param.value) for param in params] if params else ()),
        )

    @staticmethod
    def _get_mlflow_logger(trainer: Trainer) -> Optional[MLFlowLogger]:
        for logger in trainer.loggers:
            if isinstance(logger, MLFlowLogger):
                return logger
        return None

    @staticmethod
    def _update_duration_metric(metric: DurationMetric, timestamp: DateTime) -> MetricKV:
        metric.update(timestamp)

        return MetricKV(
            key=metric.metric_name,
            value=metric.elapsed_seconds,
        )
