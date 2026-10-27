// One shared promise per heavy scene chunk, so the preloader can count the
// download and the section that uses it does not fetch it twice.
let hopper: Promise<typeof import("./hopper/scene")> | null = null;

export const loadHopper = () => (hopper ??= import("./hopper/scene"));
