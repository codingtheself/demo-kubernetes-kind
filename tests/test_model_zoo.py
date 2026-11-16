"""
Unit tests for model_zoo package using standard library unittest.
Tests instantiation, shape handling, fit, predict, and checkpoint roundtripping
for all registered models.
"""

import os
import tempfile
import unittest
import numpy as np
from model_zoo.registry import list_available_models, get_model


class TestModelZoo(unittest.TestCase):

    def _test_single_model(self, model_key: str):
        lookback = 12
        model = get_model(model_key, lookback=lookback)
        self.assertEqual(model.lookback, lookback)
        self.assertIsNotNone(model.name)

        # Mock dataset: 100 samples
        np.random.seed(42)
        X = np.random.uniform(0.1, 0.9, size=(100, lookback, 1)).astype(np.float32)
        y = np.random.uniform(0.1, 0.9, size=(100,)).astype(np.float32)

        # Fit
        history = model.fit(X, y, epochs=2, batch_size=32, verbose=False)
        self.assertIsNotNone(history)

        # Predict Batch
        preds = model.predict_batch(X[:10])
        self.assertEqual(preds.shape, (10,))
        self.assertTrue(np.all(np.isfinite(preds)))

        # Predict Step (1D window)
        window = X[0, :, 0]  # (12,)
        single_val = model.predict_step(window)
        self.assertIsInstance(single_val, float)
        self.assertTrue(np.isfinite(single_val))

        # Parameter count
        params = model.count_parameters()
        self.assertGreaterEqual(params, 0)

        # Checkpoint Save & Load roundtrip
        ext = ".pkl" if not model.is_neural else ".pt"
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp_path = tmp.name

        try:
            model.save(tmp_path)
            self.assertTrue(os.path.exists(tmp_path))

            # Fresh instance
            fresh_model = get_model(model_key, lookback=lookback)
            fresh_model.load(tmp_path)

            fresh_preds = fresh_model.predict_batch(X[:10])
            np.testing.assert_allclose(preds, fresh_preds, rtol=1e-4, atol=1e-4)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_all_registered_models(self):
        models = list_available_models()
        self.assertTrue(len(models) >= 7)
        for m in models:
            with self.subTest(model=m):
                self._test_single_model(m)


if __name__ == "__main__":
    unittest.main()
