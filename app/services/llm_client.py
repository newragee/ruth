import httpx
from loguru import logger

class LLMClient:
    def __init__(self, model_name: str = "gemma3:4b", host: str = "http://localhost:11434"):
        self.model_name = model_name
        self.base_url = host.rstrip('/')
        logger.info(f"Клиент Ollama для модели {model_name}")

    async def generate_json(self, prompt: str, system: str = "") -> str:
        """Запрос с принудительным JSON-выводом (Ollama format=json)."""
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "system": system,
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.0, "num_predict": 256},
        }
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(f"{self.base_url}/api/generate", json=payload)
                resp.raise_for_status()
                return (resp.json().get("response") or "").strip()
        except Exception as e:
            logger.error(f"LLM JSON-запрос упал: {e}")
            return ""

    async def generate_response(self, prompt: str, context: str = "") -> str:
        full_prompt = f"{context}\n\n{prompt}" if context else prompt
        payload = {
            "model": self.model_name,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_predict": 512
            }
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(f"{self.base_url}/api/generate", json=payload)
                response.raise_for_status()
                data = response.json()

                
                answer = data.get("response", "").strip()
                if not answer:
                    # Некоторые модели возвращают ответ в поле thinking
                    answer = data.get("thinking", "").strip()
                    if answer:
                        logger.info("Ответ получен из поля thinking")
                    else:
                        logger.warning("Ollama вернула пустой ответ. Полный ответ: {data}")
                        return "Модель не дала ответа."

                return answer

        except httpx.TimeoutException:
            logger.error("Таймаут при обращении к Ollama")
            return "Ошибка: превышено время ожидания ответа от модели."
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP ошибка от Ollama: {e.response.status_code} - {e.response.text}")
            return f"Ошибка сервера модели: {e.response.status_code}"
        except Exception as e:
            logger.error(f"Неизвестная ошибка при запросе к Ollama: {e}")
            return f"Ошибка: {str(e)}"
