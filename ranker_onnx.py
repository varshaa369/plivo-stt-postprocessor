from typing import List, Tuple
import numpy as np

# Optional imports guarded to allow partial environments
try:
    import onnxruntime as ort  # type: ignore
except Exception:
    ort = None

try:
    import torch
    from transformers import AutoTokenizer, AutoModelForMaskedLM
except Exception:
    torch = None
    AutoTokenizer = None
    AutoModelForMaskedLM = None

class PseudoLikelihoodRanker:
    def __init__(self, model_name: str = "distilbert-base-uncased", onnx_path: str = None, device: str = "cpu", max_length: int = 32):
        """
        OPTIMIZATION: Reduced max_length from 64 to 32 for 2x speedup
        Most utterances in this domain are short (<30 tokens)
        """
        self.max_length = max_length
        self.model_name = model_name
        self.onnx = None
        self.torch_model = None
        self.device = device
        self.tokenizer = None
        if onnx_path and ort is not None:
            self._init_onnx(onnx_path)
        elif AutoTokenizer is not None and AutoModelForMaskedLM is not None:
            self._init_torch()
        else:
            raise RuntimeError("Neither onnxruntime nor transformers/torch are available. Please install requirements.")

    def _init_onnx(self, onnx_path: str):
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        sess_options = ort.SessionOptions()
        # OPTIMIZATION: Limit threads for faster single-sample inference
        sess_options.intra_op_num_threads = 2
        sess_options.inter_op_num_threads = 2
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.onnx = ort.InferenceSession(onnx_path, sess_options=sess_options, providers=['CPUExecutionProvider'])

    def _init_torch(self):
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.torch_model = AutoModelForMaskedLM.from_pretrained(self.model_name)
        self.torch_model.eval()
        self.torch_model.to(self.device)

    def _batch_mask_positions(self, input_ids: np.ndarray, attn: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Create a batch of masked sequences, one for each non-special token position"""
        mask_id = self.tokenizer.mask_token_id
        seq = input_ids[0]  # [1, L]
        L = int(attn[0].sum())
        positions = list(range(1, L-1))  # skip [CLS] and [SEP]
        
        if len(positions) == 0:
            # Edge case: very short sequence
            return input_ids, attn, np.array([], dtype=np.int64)
        
        batch = np.repeat(seq[None, :], len(positions), axis=0)
        for i, pos in enumerate(positions):
            batch[i, pos] = mask_id
        batch_attn = np.repeat(attn, len(positions), axis=0)
        return batch, batch_attn, np.array(positions, dtype=np.int64)

    def _score_with_onnx(self, text: str) -> float:
        """
        OPTIMIZED: Use batched masking for ~10-20x speedup
        Instead of N forward passes (one per token), do 1 forward pass with batch=N
        """
        toks = self.tokenizer(text, return_tensors="np", truncation=True, max_length=self.max_length, padding='max_length')
        input_ids = toks["input_ids"]
        attn = toks["attention_mask"]
        
        batch, batch_attn, positions = self._batch_mask_positions(input_ids, attn)
        
        if len(positions) == 0:
            # Very short text, return neutral score
            return 0.0
        
        ort_inputs = {
            "input_ids": batch.astype(np.int64), 
            "attention_mask": batch_attn.astype(np.int64)
        }
        
        # Single forward pass for all masked positions
        logits = self.onnx.run(None, ort_inputs)[0]  # [B, L, V]
        
        # Gather log-probs at the original token for each masked position
        orig = np.repeat(input_ids, len(positions), axis=0)
        rows = np.arange(len(positions))
        cols = positions
        token_ids = orig[rows, cols]
        
        # Log-softmax per row at the masked position
        logits_pos = logits[rows, cols, :]  # [B, V]
        m = logits_pos.max(axis=1, keepdims=True)
        log_probs = logits_pos - m - np.log(np.exp(logits_pos - m).sum(axis=1, keepdims=True))
        
        picked = log_probs[np.arange(len(rows)), token_ids]
        return float(picked.sum())  # higher = better

    def _score_with_torch(self, text: str) -> float:
        import torch
        toks = self.tokenizer(text, return_tensors="pt", truncation=True, max_length=self.max_length, padding='max_length').to(self.device)
        input_ids = toks["input_ids"]
        attn = toks["attention_mask"]
        
        # batch mask
        seq = input_ids[0]
        L = int(attn.sum())
        positions = list(range(1, L-1))
        
        if len(positions) == 0:
            return 0.0
        
        batch = seq.unsqueeze(0).repeat(len(positions), 1)
        for i, pos in enumerate(positions):
            batch[i, pos] = self.tokenizer.mask_token_id
        batch_attn = attn.repeat(len(positions), 1)
        
        with torch.no_grad():
            out = self.torch_model(input_ids=batch, attention_mask=batch_attn).logits  # [B, L, V]
            orig = seq.unsqueeze(0).repeat(len(positions), 1)
            rows = torch.arange(len(positions))
            cols = torch.tensor(positions)
            token_ids = orig[rows, cols]
            logits_pos = out[rows, cols, :]
            log_probs = logits_pos.log_softmax(dim=-1)
            picked = log_probs[torch.arange(len(rows)), token_ids]
        return float(picked.sum().item())

    def score(self, sentences: List[str]) -> List[float]:
        return [self._score_with_onnx(s) if self.onnx is not None else self._score_with_torch(s) for s in sentences]

    def choose_best(self, candidates: List[str]) -> str:
        if len(candidates) == 1:
            return candidates[0]
        scores = self.score(candidates)
        i = int(np.argmax(scores))
        return candidates[i]
