// Measures the long jump from s6 to s7 in a simulated run.
// The jump is decided on the first frame the player is back down at the far
// platform's top: if the box overlaps the platform there it lands, otherwise it
// drops past the edge. "Reach" is the front of the box on that frame and
// margin = reach - far edge (negative means it came up short).
import { PLAYER_HALF } from "../base/src/physics.js";

export function gapReport(level, result, nearId = "s6", farId = "s7") {
  const near = level.platforms.find((p) => p.id === nearId);
  const far = level.platforms.find((p) => p.id === farId);
  const frames = result.frames;

  // the jump that leaves s6: the first upward frame once the player is on it
  const takeoff = frames.findIndex((fr) => fr.vel[1] > 0 && fr.pos[0] >= near.min[0]);
  if (takeoff < 0) return null;
  for (let k = takeoff + 1; k < frames.length; k++) {
    if (frames[k].pos[1] > far.max[1]) continue;
    const reach = frames[k].pos[0] + PLAYER_HALF;
    return {
      takeoffFrame: takeoff,
      takeoffX: frames[takeoff].pos[0],
      downFrame: k,
      centre: frames[k].pos[0],
      reach,
      margin: reach - far.min[0],
    };
  }
  return null;
}
