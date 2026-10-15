"""Optional utterance-level Pipecat pipeline, not an always-listening transport."""
import asyncio
from dataclasses import dataclass

from pipecat.frames.frames import DataFrame, EndFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask
from pipecat.processors.frame_processor import FrameProcessor

from app.schemas import CommandRequest, CommandResponse


@dataclass
class UtteranceFrame(DataFrame):
    text: str
    language: str
    audio: bytes | None = None


@dataclass
class CommandFrame(DataFrame):
    command: CommandRequest


@dataclass
class ResultFrame(DataFrame):
    response: CommandResponse


class TranscriptionProcessor(FrameProcessor):
    def __init__(self, transcriber):
        super().__init__()
        self.transcriber = transcriber

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, UtteranceFrame):
            text = frame.text
            if frame.audio is not None:
                if self.transcriber is None:
                    raise ValueError("Enable an ASR backend for audio frames")
                text, _ = await asyncio.to_thread(self.transcriber.transcribe, frame.audio, frame.language)
            await self.push_frame(CommandFrame(CommandRequest(text=text, language=frame.language)), direction)
        else:
            await self.push_frame(frame, direction)


class IntentActionProcessor(FrameProcessor):
    def __init__(self, engine):
        super().__init__()
        self.engine = engine

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, CommandFrame):
            result = await asyncio.to_thread(self.engine.execute, frame.command)
            await self.push_frame(ResultFrame(result), direction)
        else:
            await self.push_frame(frame, direction)


class ResultCollector(FrameProcessor):
    def __init__(self):
        super().__init__()
        self.results = []

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, ResultFrame):
            self.results.append(frame.response)
        await self.push_frame(frame, direction)


async def run_utterance(engine, transcriber, text="", language="en", audio=None):
    collector = ResultCollector()
    pipeline = Pipeline([TranscriptionProcessor(transcriber), IntentActionProcessor(engine), collector])
    task = PipelineTask(pipeline, enable_rtvi=False, enable_turn_tracking=False, idle_timeout_secs=None)
    await task.queue_frames([UtteranceFrame(text=text, language=language, audio=audio), EndFrame()])
    runner = PipelineRunner(handle_sigint=False)
    await asyncio.wait_for(runner.run(task), timeout=180)
    if not collector.results:
        raise RuntimeError("Pipecat produced no result; inspect its pipeline logs")
    return collector.results[0]
