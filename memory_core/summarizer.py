import core.ollama_chat

class Summarizer:
    """
    Run summary/merge tasks through the LLM using prompt templates.
    """
    def __init__(self, llm, prompt_lib):
        self.llm = core.ollama_chat.OllamaChatbot()
        self.prompts = prompt_lib

    def l0_to_l1(self, chunk_text: str) -> str:
        prompt = self.prompts.format("l0_to_l1", chunk=chunk_text)
        return (self.llm.summarize_ask(prompt, stream_to_console=False) or "").strip()

    def merge_two(self, a_text: str, b_text: str) -> str:
        prompt = self.prompts.format("merge_two", a=a_text, b=b_text)
        return (self.llm.summarize_ask(prompt, stream_to_console=False) or "").strip()

    def l3_to_l4_master(self, master_text: str, a_text: str, b_text: str) -> str:
        prompt = self.prompts.format("l3_to_l4_master", master=master_text, a=a_text, b=b_text)
        return (self.llm.summarize_ask(prompt, stream_to_console=False) or "").strip()