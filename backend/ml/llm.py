"""
LLM service using free open-source models
Uses TinyLlama for fast inference without GPU requirements
For production, can swap with larger models like Mistral-7B or Llama-2-7B
"""
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
import torch
from typing import Optional, List, Dict
import logging

from backend.config import settings

logger = logging.getLogger(__name__)


class LLMService:
    """
    Local LLM service using HuggingFace transformers
    Free and open-source, runs locally
    """

    def __init__(self):
        self.model_name = settings.LLM_MODEL
        self.tokenizer: Optional[AutoTokenizer] = None
        self.model: Optional[AutoModelForCausalLM] = None
        self.pipe = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

    async def initialize(self):
        """Load LLM model"""
        logger.info(f"Loading LLM model: {self.model_name} on {self.device}")

        try:
            # Load tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)

            # Load model with appropriate settings for CPU/GPU
            if self.device == "cpu":
                # CPU optimization
                self.model = AutoModelForCausalLM.from_pretrained(
                    self.model_name,
                    torch_dtype=torch.float32,
                    low_cpu_mem_usage=True
                )
            else:
                # GPU optimization
                self.model = AutoModelForCausalLM.from_pretrained(
                    self.model_name,
                    torch_dtype=torch.float16,
                    device_map="auto"
                )

            # Create pipeline
            self.pipe = pipeline(
                "text-generation",
                model=self.model,
                tokenizer=self.tokenizer,
                device=0 if self.device == "cuda" else -1
            )

            logger.info("LLM model loaded successfully")

        except Exception as e:
            logger.warning(f"Could not load LLM model: {e}. LLM features will be limited.")
            # Graceful degradation - system can still work without LLM

    def generate(
        self,
        prompt: str,
        max_length: int = 200,
        temperature: float = 0.7,
        top_p: float = 0.9,
        **kwargs
    ) -> str:
        """
        Generate text completion
        """
        if not self.pipe:
            return "LLM not available. Please initialize the model."

        try:
            # Format prompt for chat model
            if "chat" in self.model_name.lower():
                formatted_prompt = f"<|user|>\n{prompt}</s>\n<|assistant|>\n"
            else:
                formatted_prompt = prompt

            # Generate
            result = self.pipe(
                formatted_prompt,
                max_length=max_length,
                temperature=temperature,
                top_p=top_p,
                do_sample=True,
                num_return_sequences=1,
                **kwargs
            )

            generated_text = result[0]["generated_text"]

            # Extract just the response (remove prompt)
            if formatted_prompt in generated_text:
                generated_text = generated_text.replace(formatted_prompt, "").strip()

            return generated_text

        except Exception as e:
            logger.error(f"Error generating text: {e}")
            return f"Error: {str(e)}"

    def answer_question(
        self,
        question: str,
        context: str,
        max_length: int = 150
    ) -> str:
        """
        Answer question given context (RAG pattern)
        """
        prompt = f"""Based on the following context, answer the question concisely.

Context: {context}

Question: {question}

Answer:"""

        return self.generate(prompt, max_length=max_length, temperature=0.3)

    def extract_entities(self, text: str) -> Dict[str, List[str]]:
        """
        Extract named entities from text
        Simple rule-based extraction as fallback if LLM not available
        """
        # This is a simplified version - in production would use proper NER
        prompt = f"""Extract medical entities from this text. List them as:
- Providers: [list]
- Locations: [list]
- Specialties: [list]

Text: {text}

Entities:"""

        if self.pipe:
            result = self.generate(prompt, max_length=200, temperature=0.1)
            # Parse result (simplified)
            return {"extracted": result}
        else:
            return {"error": "LLM not available"}

    def generate_query_plan(self, natural_language_query: str) -> Dict[str, any]:
        """
        Convert natural language query to structured query plan
        """
        prompt = f"""Convert this natural language query into a structured search plan.

Query: {natural_language_query}

Return a JSON-like structure with:
- intent: what the user wants
- entities: key entities mentioned
- filters: what filters to apply
- actions: what operations to perform

Plan:"""

        if self.pipe:
            result = self.generate(prompt, max_length=250, temperature=0.2)
            return {"plan": result}
        else:
            return {
                "intent": "search",
                "entities": [],
                "filters": {},
                "actions": ["search"]
            }


# Global singleton
llm_service = LLMService()
