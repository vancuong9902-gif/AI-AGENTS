from dataclasses import dataclass, field


@dataclass
class MetricsCollector:
    counters: dict[str, int] = field(default_factory=dict)

    def inc(self, key: str, value: int = 1) -> None:
        self.counters[key] = self.counters.get(key, 0) + value
