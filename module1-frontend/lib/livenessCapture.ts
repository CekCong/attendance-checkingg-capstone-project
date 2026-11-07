import type { LivenessTicket } from "./studentApi";

export const ACTION_GUIDANCE = {
  blink: "Close both eyes gently for two seconds, then open them. Keep your head still.",
  head_turn: "Turn slightly to one side and hold. Keep both eyes in the picture; do not turn into profile.",
  smile: "Smile and hold it until asked to relax your face.",
};

type CaptureControls = {
  assertActive: () => void;
  prompt: (title: string, detail: string, countdown: number | null, stage: number) => void;
  capture: () => string;
  wait: (milliseconds: number) => Promise<void>;
};

/** Keep the server's 15-frame contract, allowing time to understand each instruction. */
export async function captureLivenessSequence(
  action: LivenessTicket["challenge_type"],
  controls: CaptureControls,
): Promise<string[]> {
  const frames: string[] = [];
  const pause = async (milliseconds: number) => {
    controls.assertActive();
    await controls.wait(milliseconds);
    controls.assertActive();
  };
  try {
    for (let seconds = 3; seconds > 0; seconds--) {
      controls.prompt("Get ready — start with a neutral face", `Coming next: ${ACTION_GUIDANCE[action]}`, seconds, 0);
      await pause(1000);
    }
    const stages = [
      ["1 of 3 · Look straight ahead", "Keep your eyes open and your mouth relaxed."],
      ["2 of 3 · " + ({ blink: "Close your eyes", head_turn: "Turn your head slightly", smile: "Smile" }[action]), ACTION_GUIDANCE[action]],
      ["3 of 3 · Return to neutral", "Face forward, open your eyes and relax your mouth. Hold still."],
    ];
    for (let stage = 0; stage < stages.length; stage++) {
      controls.prompt(stages[stage][0], stages[stage][1], null, stage + 1);
      // Give the student time to react before recording this phase.
      await pause(1000);
      for (let index = 0; index < 5; index++) {
        controls.prompt(stages[stage][0], stages[stage][1], Math.ceil((5 - index) * 0.4), stage + 1);
        await pause(400);
        frames.push(controls.capture());
      }
    }
    return frames;
  } catch (error) {
    frames.length = 0;
    throw error;
  }
}
