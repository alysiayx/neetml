from .config import NEETMLConfig

__all__ = [
    "NEETMLConfig",
    "DataPreprocessor",
    "FeatureEngineer",
    "ModelTrainer",
]


def __getattr__(name: str):
    """Load workflow classes only when requested."""
    if name == "DataPreprocessor":
        from .preprocessing import DataPreprocessor

        return DataPreprocessor
    if name == "FeatureEngineer":
        from .features import FeatureEngineer

        return FeatureEngineer
    if name == "ModelTrainer":
        from .modeling.trainer import ModelTrainer

        return ModelTrainer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
