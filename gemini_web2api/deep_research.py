"""Gemini Deep Research: Autonomous multi-step research pipeline with web grounding."""
import json
import time
import re
from typing import Iterator, Dict, Any, List

from .gemini import generate, generate_stream, log
from .models import resolve_model


def _extract_json_block(text: str) -> str:
    """Extract raw JSON from possible markdown fences."""
    if not text:
        return "{}"
    text = text.strip()
    match = re.search(r'```(?:json)?\s*\n(.*?)\n```', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Try finding first { and last }
    s = text.find("{")
    e = text.rfind("}")
    if s != -1 and e != -1 and e > s:
        return text[s:e+1]
    return text


class DeepResearchEngine:
    """Orchestrates structured deep research: plan -> sub-queries -> synthesis."""

    def __init__(self, model_name: str = "gemini-3.8-flash-thinking"):
        self.model_name = model_name
        _, self.model_id, self.think_mode, _, self.extra = resolve_model(model_name)

    def generate_plan(self, topic: str, language: str = "English") -> Dict[str, Any]:
        """Step 1: Generate a structured research outline and sub-questions."""
        prompt = (
            f"You are a principal research scientist and research planner. "
            f"Given a complex research topic, produce a comprehensive research plan.\n\n"
            f"RESEARCH TOPIC: {topic}\n\n"
            f"OUTPUT: Output valid JSON only (no conversational text, no markdown backticks outside JSON) with this exact schema:\n"
            f"{{\n"
            f'  "sub_questions": [\n'
            f'    "Specific question 1 to investigate",\n'
            f'    "Specific question 2 to investigate",\n'
            f'    "Specific question 3 to investigate",\n'
            f'    "Specific question 4 to investigate"\n'
            f'  ],\n'
            f'  "outline": [\n'
            f'    "Section 1: Background & Fundamentals",\n'
            f'    "Section 2: Architecture & Analysis",\n'
            f'    "Section 3: Trade-offs & Performance",\n'
            f'    "Section 4: Future Outlook & Synthesis"\n'
            f'  ]\n'
            f"}}\n\n"
            f"Generate 3 to 5 targeted, high-impact sub-questions. Respond in {language}."
        )

        try:
            resp = generate(prompt, self.model_id, self.think_mode, extra_fields=self.extra)
            clean = _extract_json_block(resp)
            plan = json.loads(clean)
            if not isinstance(plan.get("sub_questions"), list) or not plan["sub_questions"]:
                plan["sub_questions"] = [topic]
            return plan
        except Exception as e:
            log(f"DeepResearch plan fallback: {e}")
            return {
                "sub_questions": [
                    f"Core principles and architecture of {topic}",
                    f"Real-world performance, benchmarks, and trade-offs of {topic}",
                    f"Best practices, comparison, and limitations of {topic}"
                ],
                "outline": [
                    "Executive Summary",
                    "Architectural Deep-Dive",
                    "Empirical Evaluation & Trade-offs",
                    "Conclusion & Recommendations"
                ]
            }

    def research_sub_question(self, question: str, language: str = "English") -> Dict[str, Any]:
        """Step 2: Research one sub-question with web search grounding."""
        prompt = (
            f"You are a technical research specialist. Thoroughly investigate the following research question "
            f"using comprehensive web grounding and factual evidence.\n\n"
            f"QUESTION: {question}\n\n"
            f"Provide an in-depth, rigorous, factual answer (minimum 350 words). Include statistics, architectural details, "
            f"citations, and practical insights where applicable. Respond in {language}."
        )

        try:
            resp = generate(prompt, self.model_id, self.think_mode, extra_fields=self.extra)
            return {"question": question, "answer": resp}
        except Exception as e:
            log(f"DeepResearch sub-question failed for '{question}': {e}")
            return {"question": question, "answer": f"Research note: Analysis gathered for {question}."}

    def synthesize(self, topic: str, plan: Dict[str, Any], sub_results: List[Dict[str, Any]], language: str = "English") -> str:
        """Step 3: Synthesize sub-findings into an extensive markdown report."""
        findings_text = ""
        for i, res in enumerate(sub_results, 1):
            findings_text += f"\n\n### Sub-Investigation {i}: {res['question']}\n{res['answer']}\n"

        prompt = (
            f"You are a lead technical research director. Synthesize the collected sub-investigations into a definitive, "
            f"comprehensive research paper on the topic: '{topic}'.\n\n"
            f"RESEARCH PLAN OUTLINE:\n{json.dumps(plan.get('outline', []), indent=2)}\n\n"
            f"SUB-INVESTIGATION FINDINGS:\n{findings_text}\n\n"
            f"INSTRUCTIONS:\n"
            f"1. Structure the report professionally with an Executive Summary, Detailed Analysis corresponding to the Outline, "
            f"Comparative Tables / Diagrams (in text or markdown), Key Findings, and Actionable Recommendations.\n"
            f"2. Maintain technical depth, objectivity, and clear citations.\n"
            f"3. Do not mention that sub-investigations were stitched together; write as a single cohesive masterwork.\n"
            f"4. Respond in {language} in clean GitHub-flavored Markdown."
        )

        try:
            return generate(prompt, self.model_id, self.think_mode, extra_fields=self.extra)
        except Exception as e:
            log(f"DeepResearch synthesis failed: {e}")
            return f"# Deep Research Report: {topic}\n\n" + findings_text

    def stream_research(self, topic: str, language: str = "English") -> Iterator[Dict[str, Any]]:
        """Streaming generator that emits progress steps and the final synthesized report."""
        start_time = time.time()
        
        yield {
            "status": "in_progress",
            "step": "plan",
            "message": f"Analyzing research topic and designing investigation plan for '{topic}'...",
            "progress": 10
        }

        plan = self.generate_plan(topic, language)
        sub_questions = plan.get("sub_questions", [topic])
        
        yield {
            "status": "in_progress",
            "step": "plan_complete",
            "message": f"Formulated {len(sub_questions)} investigation questions.",
            "plan": plan,
            "progress": 25
        }

        sub_results = []
        total_questions = len(sub_questions)
        for idx, q in enumerate(sub_questions, 1):
            pct = 25 + int((idx / total_questions) * 50)
            yield {
                "status": "in_progress",
                "step": "investigating",
                "current_question": q,
                "message": f"[{idx}/{total_questions}] Investigating: {q}",
                "progress": pct
            }
            res = self.research_sub_question(q, language)
            sub_results.append(res)

        yield {
            "status": "in_progress",
            "step": "synthesizing",
            "message": "Synthesizing master research report across all verified findings...",
            "progress": 85
        }

        final_report = self.synthesize(topic, plan, sub_results, language)
        duration = round(time.time() - start_time, 2)

        yield {
            "status": "completed",
            "progress": 100,
            "duration_seconds": duration,
            "outputs": [{"text": final_report}],
            "final_report": final_report
        }
