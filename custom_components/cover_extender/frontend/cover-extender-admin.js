/**
 * Cover Extender — admin panel.
 *
 * A custom panel reached from the sidebar, from the hub device's
 * configuration_url, or at /cover-extender directly. It is the only way to
 * configure the integration: the config flow creates the entry and stops there.
 *
 * Six tabs, all editable. Four for every day, in the order of the work:
 * Covers, Modes, Matrix (modes × covers, the screen a config flow cannot
 * draw), Schedules. Two set once: House (facades, templates) and Settings
 * (the global settings, and a read-only count of what all this produced in
 * Home Assistant).
 *
 * All truth stays in Python: the panel talks to two WebSocket commands
 * (cover_extender/config/get · save) which validate through the integration's
 * own schemas and persist into the config entry options — the coordinator's
 * existing update listener then hot-reloads everything. The panel therefore
 * hard-codes no default and no bound: both come down in `config/get`.
 */

const DOMAIN = "cover_extender";

// Entity domains this integration creates helpers in. The integration page used
// to be the only place that showed how many; it no longer edits anything, so the
// count moves here — a facade or a template is abstract until you see what it
// actually produced.
const ENTITY_ICONS = {
  select:        "mdi:format-list-bulleted",
  switch:        "mdi:toggle-switch-outline",
  binary_sensor: "mdi:check-circle-outline",
  sensor:        "mdi:gauge",
};
const WS_GET = `${DOMAIN}/config/get`;
const WS_SAVE = `${DOMAIN}/config/save`;

// Focus-trap candidates inside the matrix popover. ha-selector is in the list
// because it hosts its own shadow root: focusing it hands the key to whatever
// input it wraps, which is the behaviour we want and the only one reachable
// from outside that root.
const FOCUSABLE =
  'button:not([disabled]), input, select, textarea, ha-selector, a[href], [tabindex]:not([tabindex="-1"])';

/* ---------- the words ----------

   A panel cannot read strings.json: the translation categories Home Assistant
   serves to the browser are fixed, and none of them houses a panel's prose. It
   carries its own dictionary, exactly as a distributed card does.

   The language is the READER'S — `hass.locale.language`, the one each admin
   chose for themselves — and not the server's, which is what names entities and
   composes states on the Python side.

   English is the fallback KEY BY KEY (see mergeWords): a table missing a line
   lets an English sentence through, which is seen and corrected, where a missing
   key would print "undefined" in the middle of the page. Which is also why a key
   that is the same in every language (a proper noun, a pure format) is written
   in `en` alone rather than copied about.

   Values are strings or functions. Plural, elision and word order belong to the
   language, so each table carries its own rule instead of a shared template fed
   with a count. Anything that is not prose — an icon name — stays out of here. */

const WORDS = {
  en: {
    title: "Cover Extender",
    tabs: { matrice: "Matrix", volets: "Covers", modes: "Modes", horaires: "Schedules", maison: "House", reglages: "Settings" },
    sched: {
      kinds: { morning: "Morning opening", evening: "Evening closing" },
      enable: { morning: "Morning opening on", evening: "Evening closing on" },
      enableHint: {
        morning: "Off: no morning event, and the covers keep their mode.",
        evening: "Off: no evening event, and the covers keep their mode.",
      },
      verb: { morning: "Opening", evening: "Closing" },
      ref: { morning: "sunrise", evening: "sunset" },
      refCap: { morning: "Sunrise", evening: "Sunset" },
      refLong: { morning: "sunrise", evening: "sunset" },
      refLongCap: { morning: "Sunrise", evening: "Sunset" },
      band: { morning: "Open before sunrise", evening: "Closed before sunset" },
      hi: "Max time", hiFixed: "Max time = min", lo: "Min time",
      x1: "Spring crossing", x2: "Autumn crossing",
      fl: "Not before", ce: "Not after", flShort: "not before", ceShort: "not after",
      fixedHint: "For a fixed time all year round, drag the max and min handles together until they stick.",
      dstHint: (h) => ` Here they are either together or at least ${h} h apart, because of daylight saving time.`,
      legal: "legal time", off: "off", offHalf: "off · plain half-sine",
      unusedFixed: "unused with a fixed time", glued: "stuck to max: fixed time",
      fixedAll: "fixed time all year, legal time", ignoredShort: " · ignored",
      fixedLabel: (t) => `fixed time ${t}`,
      fixedName: "Fixed time",
      editApply: "Apply",
      editBadTime: "Invalid time: type HH:MM.",
      editRange: (a, b) => `Choose a time between ${a} and ${b}.`,
      editBadDate: "Invalid date: type day, month and year.",
      today: "Today", earliest: "Earliest", latest: "Latest",
      onDate: (d) => `on ${d}`,
      beforeRef: (band, n, gap, d) => `${band}: ${n} day${n > 1 ? "s" : ""} a year, up to ${gap} on ${d}.`,
      errors: {
        schedule_min_after_max: "The min time is after the max time. For a fixed time, enter the same time in both fields.",
        schedule_floor_after_ceiling: "“Not before” must come before “not after”.",
        schedule_invalid: "These settings cannot be read.",
        schedule_no_sun: "The sun does not rise or set every day at this latitude: no curve can follow it.",
      },
      ignored: {
        out_of_range: (d, r, t) => `Crossing on ${d} ignored: that day, ${r} (${t}) is not between the min and max times.`,
        same_half: (d) => `Crossing on ${d} ignored: both crossings fall on the same half of the curve, one before the longest day and one after.`,
        too_steep: (d) => `Crossing on ${d} ignored: it would bend the curve too much. Move it closer to the equinox, or change the min or max time.`,
      },
      manyCross: (r, n) => `The curve crosses ${r} ${n} times a year. Check that this is intended.`,
      clampHiLo: "The max cannot go below the min: the handles stay together.",
      clampHiFl: (t) => `The max cannot go below “not before” (${t}).`,
      clampLoHi: "The min cannot go above the max: the handles stay together.",
      clampLoCe: (t) => `The min cannot go above “not after” (${t}).`,
      clampFlHi: (t) => `“Not before” cannot go above the max (${t}).`,
      clampFlCe: (t) => `“Not before” stays below “not after” (${t}).`,
      clampCeLo: (t) => `“Not after” cannot go below the min (${t}).`,
      clampCeFl: (t) => `“Not after” stays above “not before” (${t}).`,
      clampGap: "A curve needs at least 1 h between max and min: below that, the clock change would push it under the min in winter.",
      clampCross: (k, a, b) => `The ${k.toLowerCase()} stays between ${a} and ${b}.`,
      introShort: "Morning and evening, each cover takes the action chosen for it in the table: a mode or a position.",
      curveTitle: { morning: "Morning opening time", evening: "Evening closing time" },
      effNone: "nothing",
      effPart: (label, n) => `${label}: ${n}`,
      introInfo: "A mode applies as a mode change like any other: exclusions, inhibitions, the lock and timed modes apply. A position leaves the mode alone; it respects the lock unless it is forced, and an open window always holds it back.",
      offShort: "off",
      follows: (r, t) => (t ? `follows the ${r} (today ${t})` : `follows the ${r}`),
      grpCurve: "Curve over the year", grpBounds: "Bounds in legal time", grpFine: "Fine-tune",
      crossSum: (a, b) => `Crossings: spring ${a} · autumn ${b}`,
      no: "no",
      dragHint: "Drag the handles on the chart, or double-click one to type its value.",
      allCovers: "All covers", mixed: "Several", differs: "differs from the other covers",
      perCover: "Action applied per cover",
      perCoverSub: "“None”: the cover does not follow this schedule. A mode applies as a grouped mode change; only the modes linked to the cover and without a duration are offered. A position moves the cover without changing its mode.",
      cover: "Cover", noneOpt: "None",
      grpMode: "Mode", grpPos: "Position", posOpt: "Fixed position…", posLabel: "Position in %",
      lockedLabel: "If the cover is locked",
      keepLock: "Respects the lock", forcePos: "Force",
      keepLockHint: "Free cover: it moves. Locked cover: it does not move; the position goes to memory and the cover takes it when it leaves the locked mode.",
      forceHint: "Moves at once, even locked, and passes the inhibitions. The mode and the lock stay; the memory takes this position too, so leaving the mode does not undo it. An open window still holds it back.",
      forceComputes: "One of this cover's modes computes its position (shading, solar gain): its next computation can move the cover again.",
    },
    loading: "Loading the configuration…",
    loadError: "Could not load the configuration",
    retry: "Retry",
    facade: "Facade",
    noFacade: "No facade",
    noTemplate: "no template",
    template: "template",
    legendFixed: "Fixed position",
    legendBehavior: {
      none: "No target", auto_shade: "Shading", solar_gain: "Solar gain",
    },
    legendEntity: "Entity",
    auto: "auto",
    noTarget: "none",
    linkMode: "Add this mode",
    matrixHint: "A cell says what the mode does on that cover. Click it to change it; click an empty cell to add the mode.",
    viewList: "By cover", viewTable: "Table",
    openMode: (m) => `Open the ${m} mode`,
    // Same in every language: written here only, reached through the fallback.
    posTitle: (m, c) => `${m} · ${c}`,
    posSub: "Position applied when this mode is turned on",
    behaviorSub: {
      auto_shade: "Position computed by automatic shading",
      solar_gain: "Position computed by solar gain",
    },
    segFixed: "Fixed",
    segEntity: "Entity",
    segNone: "None",
    segAuto: "Computed",
    noneHint: "No position forced: the cover stays where it is (locked if the mode locks).",
    entityHint: "The entity's value drives the position live.",
    autoHint: "Default: the position is computed for this cover.",
    overrideHint: "Override: this cover ignores the computation while in this mode.",
    overrideTitle: "Overrides the computed position",
    applyFacade: (n, f) => `Same for the ${n} other covers on the ${f} facade`,
    applyFacadeOne: (c, f) => `Same for ${c} (${f} facade)`,
    unlink: "Remove",
    link: "Add",
    applyDraft: "Apply",
    cancel: "Cancel",
    save: "Save",
    saved: "Saved: configuration reloaded",
    saveError: "Could not save",
    // The fallback for a code no table names: the punctuation around it is
    // the language's too — French puts a space before the colon.
    rawError: (raw) => `Could not save: ${raw}`,
    discardConfirm: "Some changes have not been saved. Discard them?",
    saving: "Saving…",
    covers: (n) => `${n} cover${n > 1 ? "s" : ""}`,
    modesCount: (n) => `${n} mode${n > 1 ? "s" : ""}`,
    shading: "Shading",
    solarGain: "Solar gain",
    lock: "lock",
    hidden: "hidden",
    facades: "Facades",
    templates: "Templates",
    interval: "Pause between two covers",
    facadesSub: "The way the walls face, shared by their covers.",
    templatesSub: "The covers' starting values; each one may depart from them.",
    addFacade: "Add a facade",
    addTemplate: "Add a template",
    backToFacades: "All facades",
    backToTemplates: "All templates",
    templateTitle: "Template",
    azimuth: "Azimuth",
    intervalHint: "Gives the gateway room when several covers move together.",
    showSunFacing: "Sun facing",
    showAutoShade: "Automatic shading",
    showSolarGain: "Solar gain",
    weatherStates: {
      "clear-night": "Clear, night", cloudy: "Cloudy", exceptional: "Exceptional",
      fog: "Fog", hail: "Hail", lightning: "Lightning",
      "lightning-rainy": "Lightning, rainy", partlycloudy: "Partly cloudy",
      pouring: "Pouring", rainy: "Rainy", snowy: "Snowy",
      "snowy-rainy": "Snowy, rainy", sunny: "Sunny",
      windy: "Windy", "windy-variant": "Windy, variant",
    },
    addMode: "Add a mode",
    addCover: "Add a cover",
    dragHint: "In the order of the mode selector: drag a row to change it.",
    behaviorKind: { none: "Fixed position", auto_shade: "Follows shading", solar_gain: "Follows solar gain" },
    backToModes: "All modes",
    newMode: "New mode",
    name: "Name",
    icon: "Icon",
    color: "Color",
    behaviorHint: "The matrix can still force a position or an entity on any cover.",
    lockField: "Lock the covers",
    lockHint: "The covers stop moving; the positions asked for are remembered.",
    hiddenField: "Hide from the selector",
    hiddenHint: "The mode stays available to automations.",
    entitiesSec: "Generated entities",
    entitiesSub: "What this configuration produced in Home Assistant.",
    entityKinds: {
      select: "Mode selectors", switch: "Switches",
      binary_sensor: "Binary sensors", sensor: "Sensors",
    },
    entityTotal: (n) => `${n} entit${n > 1 ? "ies" : "y"} in total`,
    delete: "Delete",
    inUseTitle: (n) => `Used by ${n} cover${n > 1 ? "s" : ""}: remove it from them in the matrix first.`,
    inUseItemTitle: (n) => (n > 1 ? `Used by ${n} covers: move them first.` : "Used by 1 cover: move it first."),
    backToCovers: "All covers",
    entity: "Cover entity",
    picture: "Picture",
    exclusion: "Safety exclusions",
    inhibition: "Inhibitions",
    priorityField: "Priority mode",
    priorityHint: "Goes through the pauses (guests, children…), never the safety stops (open window, rain).",
    priority: "priority",
    durationField: "Limited duration",
    durationHint: "The cover leaves this mode on its own when the time is up.",
    durationLabel: "Duration",
    returnField: "When the time is up",
    returnBase: "go back to the previous mode",
    returnHint: "The previous mode is the last mode without a duration the cover was in. Only modes without a duration can be chosen here. Choosing a mode without a duration before the end stops the countdown.",
    timedChip: (n, r) => (r ? `${n} min, then ${r}` : `${n} min`),
    statusTimer: (m, t) => `back to ${m} at ${t}`,
    statusLocked: (p) => (p == null ? "locked" : `locked, ${p} % remembered`),
    schedNext: "next", schedTomorrow: (t) => `tomorrow ${t}`, schedNone: "nothing",
    schedTitle: "Schedules", schedEdit: "Change",
    coverModesTitle: "Modes of this cover", seeMatrix: "See the matrix",
    addPicture: "Add a picture",
    nav: { cover: "Cover", modes: "Modes", block: "Holds back", detection: "Sun" },
    schedOpen: "Open the Schedules tab", schedAria: (n) => `Schedules of ${n}, open the Schedules tab`,
    fcSafety: (n) => `${n}: the cover moves once the exclusion clears.`,
    fcInhib: (n) => `${n}: the cover moves when the inhibition ends.`,
    fcMemory: (p) => `Locked: ${p} % goes to memory, taken when it leaves the mode.`,
    fcRecompute: "Its current mode computes the position: the next computation can move it again.",
    fcSpared: (cur, m) => `${m} does not replace ${cur}: the cover stays in ${cur}.`,
    fcAfterTimed: (cur, m) => `${m} will apply when ${cur} ends.`,
    entitiesShow: "Show the entities",
    groupedTitle: "Applied to several covers",
    groupedHint: "Global selector, schedules, automations. A choice made on one cover's own selector always applies.",
    groupedInfo: "The apply_mode action with force: true goes through as well.",
    sparesField: "Leave alone the covers in",
    sparesHint: "A cover in a timed mode is left alone too, and takes this mode when its time is up.",
    sparesNone: "No mode: this one replaces every other.",
    sparesAdd: "+ mode",
    sparesChip: (names) => (names.length <= 2 ? `spares ${names.join(", ")}` : `spares ${names.length} modes`),
    fallbackChip: (m) => `else ${m}`,
    fallbackField: "The covers without this mode in the matrix switch to",
    fallbackHint: "E.g. Away, then Automatic on the covers that have no Away.",
    fallbackNone: "nothing (they stay)",
    usedAsReturn: (names) => `This mode is the one ${names.map((n) => `“${n}”`).join(", ")} returns to: it cannot have a duration while it is.`,
    noTemplateOpt: "No template",
    overrides: (n) => `${n} override${n > 1 ? "s" : ""}`,
    revertTitle: "Back to the template's value",
    sections: { geometry: "Geometry", detection: "Detection", shading: "Shading", solar_gain: "Solar gain" },
    fields: {
      angle_left: "Angle to the left", angle_right: "Angle to the right",
      shade_distance: "Distance from the cover", shade_max_height: "Maximum height",
      shade_min_height: "Minimum height",
      shade_min_elevation: "Minimum elevation", shade_max_elevation: "Maximum elevation",
      shade_minimum_position: "Minimum position", shade_default_position: "Default position",
      shade_change_threshold: "Change threshold", shade_time_out: "Time-out",
      solar_gain_position_solar: "Position in the sun", solar_gain_position_cold: "Position when cold",
      shade_enable: "Automatic shading enabled", solar_gain_enable: "Solar gain enabled",
      shade_sun_position: "Position in direct sun",
    },
    /* A window in a roof: the same numbers, measured along the slope. */
    fieldsRoof: { shade_max_height: "Glass length", shade_min_height: "Minimum length" },
    /* ---- editors, 4.0 layout ---- */
    inSelector: "In the selector:",
    colorPick: "Pick a color",
    colorHex: "Hexadecimal color code",
    behaviorTitle: "Cover positions",
    behaviorCardSub: "How this mode sets the position of each cover.",
    behaviorOpts: {
      none: ["Fixed", "set in the matrix"],
      auto_shade: ["Shading", "follows the sun"],
      solar_gain: ["Solar gain", "lets the sun in"],
    },
    whileTitle: "While this mode is on",
    whileSub: "As long as the cover is in this mode.",
    timedFor: "For",
    timedThen: "min, then",
    advanced: "Advanced",
    advSummary: (prio, hidden) => `${prio ? "priority" : "not priority"} · ${hidden ? "hidden" : "visible"}`,
    picturePh: "/local/… (optional)",
    blockTitle: "What holds the cover back",
    blockSub: "What was asked meanwhile is applied once the entity turns off.",
    safetyTitle: "Safety: nothing moves",
    safetySub: "Even a priority mode waits.",
    safetyEx: "E.g. an open window, a rain sensor.",
    pauseTitle: "Pause: Cover Extender keeps off",
    pauseSub: "A priority mode still goes through.",
    pauseEx: "E.g. guests, children, a “Wednesday morning” template sensor.",
    addEntity: "Add an entity",
    removeEntity: "Remove",
    calcTitle: "Position computation",
    calcFrom: "Values of the template",
    calcExcept: ", except",
    calcNoOwn: ", with no override",
    noTplChip: "No template: every value belongs to this cover.",
    openTemplate: "Open the template",
    sectionTitles: {
      geometry: "Window geometry", detection: "When the sun faces it",
      shading: "Shading", solar_gain: "Solar gain",
    },
    sectionSubs: {
      geometry: "To know how far the sun reaches into the room.",
      detection: "Where the sun must be: one sector for everything, a range of heights for shading.",
      shading: "The cover comes down just enough when the sun is in front.",
      solar_gain: "Let the sun in when it is cool and fine. Temperature and weather: Settings tab.",
    },
    fieldHints: {
      shade_distance: "How far direct light may reach, on the floor.",
      shade_max_height: "Bottom of the cover when open (100 %).",
      shade_min_height: "Bottom of the cover when closed: 0 for a French window.",
      angle_left: "Towards the east for a south facade.",
      angle_right: "Towards the west for a south facade.",
      shade_minimum_position: "Shading never closes further than this.",
      shade_default_position: "When the sun is not in front of the window.",
      shade_change_threshold: "Small moves are skipped, to spare the motor.",
      shade_time_out: "Wait after any move of the cover, by hand included.",
      solar_gain_position_solar: "Cool, fine weather, sun in front.",
      solar_gain_position_cold: "Cool, but no sun on the window or bad weather.",
      shade_sun_position: "Flat windows only: the sun falls straight in, so the cover takes this position while the sun reaches the glass.",
    },
    fieldHintsRoof: {
      shade_distance: "How far direct light may reach, measured at the level of the glass's lower edge.",
      shade_max_height: "Along the slope, from the bottom to the top of the glazing (cover open, 100 %).",
      shade_min_height: "Cover closed: 0 for most roof windows.",
    },
    fromTemplate: (v) => `template: ${v}`,
    ovrLabel: "Override",
    backToTpl: "Back to the template",
    inheritedTitle: (n) => `Value of the ${n} template: change it to override it on this cover.`,
    filterAll: "All",
    filterOwn: (n) => `Overrides only (${n})`,
    noOwn: "No override: this cover follows its template everywhere.",
    elevationRange: "Sun height",
    elevationHint: "Outside this range the cover goes to its default position.",
    elevationHintRoof: "Read from the horizon in front, over the zenith (90°), down to the roof: 120° is 60° behind.",
    elevEnds: ["horizon, in front", "zenith", "the roof, behind"],
    rangeTo: "to",
    fig: {
      outside: "outside", room: "room", max: "max height", min: "min height",
      distance: "distance", left: "left", right: "right", view: "seen from inside",
      top: "from above", side: "in profile", section: "cross-section", horizon: "horizon",
      sectorSun: "solar gain, sensor and shading", sectorShade: "heights for shading", sunNow: "the sun now",
      behindRoof: "behind: only above the roof", wholeSky: "the whole sky, any direction", behind: "behind",
      length: "length",
    },
    detGroupSun: "Solar gain, the “sun facing” sensor and shading",
    detGroupShade: "Shading",
    tplName: "Template name",
    usedBy: "Used by",
    noCoverYet: "No cover yet",
    tplFacades: (list) => `Facades of this type: ${list}.`,
    tplNoFacade: "No facade of this type yet.",
    facadeName: "Facade name",
    facadeCovers: "Covers on this facade",
    orientTitle: "Orientation",
    orientSub: "Where the windows look, seen from inside.",
    dragCompass: "or turn the compass",
    compassNote: "The window is at the top, seen from inside: the letters turn around the house, the arrow stays. Yellow is where the sun can face the facade.",
    compassLeft: "to the left",
    sectorRange: "Sector",
    sectorHint: "Where the sun counts as in front of the window, either side of its axis.",
    sectorEnds: ["← left", "window's axis", "right →"],
    compassRight: "to the right",
    slopeTitle: "Slope",
    slopeSub: "The glass's angle with the horizontal.",
    slopeKinds: { wall: "Wall", roof: "Roof", flat: "Flat" },
    kindNoun: { wall: "a wall", roof: "a roof", flat: "a flat window" },
    tplKind: "For windows on",
    tplKindRef: (t, house) => `Drawn on a ${t}° roof${house ? ", the flattest of the house's roofs" : ""}.`,
    tplKindMismatch: (t, tk, fk) => `Template “${t}” is meant for ${tk}, not ${fk}: pick another one, or none.`,
    tplKindUsers: (list) => `Covers using it sit on a facade of another type: ${list}. Saving will be refused.`,
    facadeKindUsers: (list) => `These covers have a template for another type of window: ${list}. Change their template first.`,
    facadeDir: "Where the window faces",
    slopeAria: "Slope, in degrees",
    slopeNotes: {
      wall: "An upright window sees only the sky in front of it. Roof and Flat let the sun in from behind too; a roof window is set by its glass's length instead of heights, a flat one by a position in the sun.",
      roof: "A roof window also sees part of the sky behind it: the sun reaches the glass once it is higher than the slope.",
      flat: "A flat skylight sees the whole sky: the sun reaches it as soon as it is up, from any direction. The azimuth no longer matters.",
    },
    slopeShort: (t) => (t >= 90 ? "" : t < 10 ? "flat" : `roof ${t}°`),
    dirs: ["N", "NE", "E", "SE", "S", "SW", "W", "NW"],
    addShort: "Add",
    tplMeta: (kind, h, d) => (kind === "flat" ? "flat" : `${kind === "roof" ? "roof · length" : "height"} ${h} m · distance ${d} m`),
    sgTitle: "Solar gain",
    sgSub: "When is it cool and fine enough to let the sun in? Applies to every cover.",
    sgThreshold: "Threshold",
    sgThrValue: "Value",
    sgThrEntity: "Entity",
    sgCoolWhen: "It is cool when",
    sgIsBelow: "is below",
    sgFineWhen: "It is fine when",
    sgReports: "reports:",
    sgMore: (n) => `+ ${n} more`,
    sgLess: "Show less",
    sgNote: "Without a temperature the first test is skipped; without weather it is always fine.",
    sgTooWarm: (t, s) => `${t} ≥ ${s}: too warm, solar gain waits`,
    sgCool: (t, s) => `${t} < ${s}: cool enough`,
    cmdTitle: "Sending commands",
    extraTitle: "Extra entities, for each cover",
    extraSub: "For your dashboards and automations.",
    showHints: {
      sun_facing: "Binary sensor: does the sun face the cover?",
      auto_shade: "Binary sensor: is shading enabled on this cover?",
      solar_gain: "Binary sensor: is solar gain enabled on this cover?",
    },
    unsaved: "Changes not saved yet",
    errors: {
      name_required: () => "The name cannot be empty.",
      name_exists: (n) => `The name “${n}” is already taken.`,
      behavior_invalid: (n) => `Invalid behavior for “${n}”.`,
      color_invalid: (n) => `Invalid color for “${n}”.`,
      duration_invalid: (n) => `Duration of “${n}”: between 1 and 1440 minutes.`,
      return_mode_invalid: (n) => `“${n}”: the mode it returns to must be an existing mode without a duration.`,
      fallback_invalid: (n) => `“${n}”: the fallback mode must be another existing mode.`,
      schedule_mode_timed: (m) => `“${m}” is applied by a schedule: it cannot have a duration, and a mode with a duration cannot be scheduled.`,
      schedule_invalid: (k) => `The ${k} schedule cannot be read.`,
      schedule_position_invalid: (e) => `${e}: a scheduled position goes from 0 to 100%.`,
      schedule_min_after_max: (k) => `The ${k} schedule: the min time is after the max time.`,
      schedule_floor_after_ceiling: (k) => `The ${k} schedule: “not before” must come before “not after”.`,
      return_mode_timed: (target, user) => `“${target}” is the mode “${user}” returns to: it cannot have a duration. Change the return of “${user}” first.`,
      in_use: (n, count, covers) => `“${n}” is still used by ${count} cover${Number(count) > 1 ? "s" : ""}: ${covers}`,
      entity_required: () => "A cover must point at an entity.",
      cover_domain: (e) => `${e} is not an entity of the cover domain.`,
      cover_exists: (e) => `Cover ${e} is already in the list.`,
      picture_invalid: (e) =>
        `${e}: the picture must be a local path (e.g. /local/my-image.png), not an external URL.`,
      facade_required: (e) => `${e}: facade missing or unknown.`,
      template_unknown: (t) => `Unknown template: ${t}`,
      mode_unknown: (m) => `Unknown mode: ${m}`,
      modes_invalid: (e) => `${e}: the mode map is unreadable.`,
      mode_cfg_invalid: (m) => `Unreadable configuration for mode ${m}.`,
      position_out_of_range: (m) => `Position out of range for mode ${m}.`,
      mode_entity_required: (m) => `Mode ${m} expects an entity.`,
      min_height_above_max: (e) => `${e}: the minimum height is above the maximum.`,
      min_elevation_above_max: (e) => `${e}: the minimum elevation is above the maximum.`,
      azimuth_invalid: (n) => `Invalid azimuth for “${n}” (0 to 360°).`,
      tilt_invalid: (n) => `Invalid slope for “${n}” (0 to 90°).`,
      window_kind_invalid: (n) => `Invalid window type for “${n}”.`,
      window_kind_mismatch: (e, t, f) => `${e}: template “${t}” and facade “${f}” are not the same type of window (wall, roof or flat).`,
      field_invalid: (f) => `Unreadable value for “${f}”.`,
      interval_invalid: () => "The interval must be between 0 and 5000 ms.",
      conditions_invalid: () => "Unreadable list of weather conditions.",
      condition_unknown: (c) => `Unknown weather condition: ${c}`,
    },
  },

  fr: {
    tabs: { matrice: "Matrice", volets: "Volets", modes: "Modes", horaires: "Horaires", maison: "Maison", reglages: "Réglages" },
    sched: {
      kinds: { morning: "Ouverture du matin", evening: "Fermeture du soir" },
      enable: { morning: "Ouverture du matin activée", evening: "Fermeture du soir activée" },
      enableHint: {
        morning: "Désactivée : pas d'événement le matin, les volets gardent leur mode.",
        evening: "Désactivée : pas d'événement le soir, les volets gardent leur mode.",
      },
      verb: { morning: "Ouverture", evening: "Fermeture" },
      ref: { morning: "lever", evening: "coucher" },
      refCap: { morning: "Lever", evening: "Coucher" },
      refLong: { morning: "lever du soleil", evening: "coucher du soleil" },
      refLongCap: { morning: "Lever du soleil", evening: "Coucher du soleil" },
      band: { morning: "Ouvert avant le lever", evening: "Fermé avant le coucher" },
      hi: "Heure max", hiFixed: "Heure max = min", lo: "Heure min",
      x1: "Croisement printemps", x2: "Croisement automne",
      fl: "Pas avant", ce: "Pas après", flShort: "pas avant", ceShort: "pas après",
      fixedHint: "Pour une heure fixe toute l'année, rapproche les poignées max et min jusqu'à ce qu'elles se collent.",
      dstHint: (h) => ` Ici, elles sont soit collées, soit écartées d'au moins ${h} h, à cause de l'heure d'été.`,
      legal: "heure légale", off: "désactivé", offHalf: "désactivé · demi-sinusoïde simple",
      unusedFixed: "inutilisé en heure fixe", glued: "collée au max : heure fixe",
      fixedAll: "heure fixe toute l'année, heure légale", ignoredShort: " · ignoré",
      fixedLabel: (t) => `heure fixe ${t}`,
      fixedName: "Heure fixe",
      editApply: "Appliquer",
      editBadTime: "Heure invalide : saisis HH:MM.",
      editRange: (a, b) => `Choisis une heure entre ${a} et ${b}.`,
      editBadDate: "Date invalide : saisis jour, mois et année.",
      today: "Aujourd'hui", earliest: "Le plus tôt", latest: "Le plus tard",
      onDate: (d) => `le ${d}`,
      beforeRef: (band, n, gap, d) => `${band} : ${n} jour${n > 1 ? "s" : ""} par an, jusqu'à ${gap} le ${d}.`,
      errors: {
        schedule_min_after_max: "L'heure min est après l'heure max. Pour une heure fixe, mets la même heure dans les deux champs.",
        schedule_floor_after_ceiling: "« Pas avant » doit précéder « pas après ».",
        schedule_invalid: "Ces réglages sont illisibles.",
        schedule_no_sun: "À cette latitude, le soleil ne se lève pas ou ne se couche pas tous les jours : aucune courbe ne peut le suivre.",
      },
      ignored: {
        out_of_range: (d, r, t) => `Croisement du ${d} ignoré : ce jour-là, le ${r} (${t}) n'est pas entre l'heure min et l'heure max.`,
        same_half: (d) => `Croisement du ${d} ignoré : les deux croisements tombent sur la même moitié de courbe, il en faut un avant le jour le plus long et un après.`,
        too_steep: (d) => `Croisement du ${d} ignoré : il demande une courbe trop déformée. Rapproche-le de l'équinoxe, ou change l'heure min ou max.`,
      },
      manyCross: (r, n) => `La courbe croise le ${r} ${n} fois dans l'année. Vérifie que c'est voulu.`,
      clampHiLo: "Le max ne descend pas sous le min : les poignées restent collées.",
      clampHiFl: (t) => `Le max ne descend pas sous « pas avant » (${t}).`,
      clampLoHi: "Le min ne monte pas au-dessus du max : les poignées restent collées.",
      clampLoCe: (t) => `Le min ne monte pas au-dessus de « pas après » (${t}).`,
      clampFlHi: (t) => `« Pas avant » ne monte pas au-dessus du max (${t}).`,
      clampFlCe: (t) => `« Pas avant » reste sous « pas après » (${t}).`,
      clampCeLo: (t) => `« Pas après » ne descend pas sous le min (${t}).`,
      clampCeFl: (t) => `« Pas après » reste au-dessus de « pas avant » (${t}).`,
      clampGap: "Entre l'heure fixe et la courbe, il faut au moins 1 h d'écart : en dessous, le changement d'heure ferait passer la courbe sous le min en hiver.",
      clampCross: (k, a, b) => `Le ${k.toLowerCase()} reste entre le ${a} et le ${b}.`,
      introShort: "Matin et soir, chaque volet applique l'action choisie pour lui dans le tableau : un mode ou une position.",
      curveTitle: { morning: "Heure de l'ouverture du matin", evening: "Heure de la fermeture du soir" },
      effNone: "rien",
      effPart: (label, n) => `${label} : ${n}`,
      introInfo: "Un mode s'applique comme tout changement de mode : les exclusions, les inhibitions, le verrou et les modes minutés s'appliquent. Une position ne change pas le mode ; elle respecte le verrou sauf si elle est forcée, et une fenêtre ouverte la bloque toujours.",
      offShort: "désactivée",
      follows: (r, t) => (t ? `suit le ${r} (aujourd'hui ${t})` : `suit le ${r}`),
      grpCurve: "Courbe sur l'année", grpBounds: "Bornes en heure légale", grpFine: "Affiner",
      crossSum: (a, b) => `Croisements : printemps ${a} · automne ${b}`,
      no: "non",
      dragHint: "Faire glisser les poignées sur le graphique, ou double-cliquer sur l'une d'elles pour taper sa valeur.",
      allCovers: "Tous les volets", mixed: "Plusieurs", differs: "diffère des autres volets",
      perCover: "Action appliquée par volet",
      perCoverSub: "« Aucune » : le volet ne suit pas cet horaire. Un mode s'applique comme un changement de mode groupé ; seuls les modes liés au volet et sans durée sont proposés. Une position déplace le volet sans changer son mode.",
      cover: "Volet", noneOpt: "Aucune",
      grpMode: "Mode", grpPos: "Position", posOpt: "Position fixe…", posLabel: "Position en %",
      lockedLabel: "Si le volet est verrouillé",
      keepLock: "Respecte le verrou", forcePos: "Force",
      keepLockHint: "Volet libre : il bouge. Volet verrouillé : il ne bouge pas, la position part en mémoire et il la prend en quittant le mode verrouillé.",
      forceHint: "Bouge tout de suite, même verrouillé, et passe outre les inhibitions. Le mode et le verrou restent ; la mémoire prend aussi cette position, pour que la sortie du mode ne l'annule pas. Une fenêtre ouverte le bloque quand même.",
      forceComputes: "Un mode de ce volet calcule sa position (ombrage, gain solaire) : son prochain calcul peut rebouger le volet.",
    },
    loading: "Chargement de la configuration…",
    loadError: "Impossible de charger la configuration",
    retry: "Réessayer",
    facade: "Façade",
    noFacade: "Sans façade",
    noTemplate: "sans gabarit",
    template: "gabarit",
    legendFixed: "Position fixe",
    legendBehavior: {
      none: "Aucune consigne", auto_shade: "Ombrage", solar_gain: "Héliotropie",
    },
    legendEntity: "Entité",
    auto: "auto",
    noTarget: "aucune",
    linkMode: "Ajouter ce mode",
    matrixHint: "Une case dit ce que fait le mode sur ce volet. Cliquer pour la changer, ou sur une case vide pour ajouter le mode.",
    viewList: "Par volet", viewTable: "Tableau",
    openMode: (m) => `Ouvrir le mode ${m}`,
    posSub: "Position appliquée quand ce mode est activé",
    behaviorSub: {
      auto_shade: "Position calculée par l'ombrage automatique",
      solar_gain: "Position calculée par l'héliotropie",
    },
    segFixed: "Fixe",
    segEntity: "Entité",
    segNone: "Aucune",
    segAuto: "Calculée",
    noneHint: "Pas de position forcée : le volet reste en place (verrouillé si le mode verrouille).",
    entityHint: "La valeur de l'entité pilote la position en direct.",
    autoHint: "Par défaut : la position est calculée pour ce volet.",
    overrideHint: "Écart : ce volet ignore le calcul dans ce mode.",
    overrideTitle: "Écart : remplace la position calculée",
    applyFacade: (n, f) => `Pareil pour les ${n} autres volets de la façade ${f}`,
    applyFacadeOne: (c, f) => `Pareil pour ${c} (façade ${f})`,
    unlink: "Retirer",
    link: "Ajouter",
    applyDraft: "Appliquer",
    cancel: "Annuler",
    save: "Enregistrer",
    saved: "Enregistré : configuration rechargée",
    saveError: "Échec de l'enregistrement",
    rawError: (raw) => `Échec de l'enregistrement : ${raw}`,
    discardConfirm: "Des modifications ne sont pas enregistrées. Les abandonner ?",
    saving: "Enregistrement…",
    covers: (n) => `${n} volet${n > 1 ? "s" : ""}`,
    modesCount: (n) => `${n} mode${n > 1 ? "s" : ""}`,
    shading: "Ombrage",
    solarGain: "Héliotropie",
    lock: "verrou",
    hidden: "masqué",
    facades: "Façades",
    templates: "Gabarits",
    interval: "Pause entre deux volets",
    facadesSub: "L'orientation des murs, partagée par leurs volets.",
    templatesSub: "Les valeurs de départ des volets ; chacun peut s'en écarter.",
    addFacade: "Ajouter une façade",
    addTemplate: "Ajouter un gabarit",
    backToFacades: "Toutes les façades",
    backToTemplates: "Tous les gabarits",
    templateTitle: "Gabarit",
    azimuth: "Azimut",
    intervalHint: "Laisse respirer la passerelle quand plusieurs volets bougent ensemble.",
    showSunFacing: "Face au soleil",
    showAutoShade: "Ombrage automatique",
    showSolarGain: "Héliotropie",
    weatherStates: {
      "clear-night": "Nuit claire", cloudy: "Nuageux", exceptional: "Exceptionnel",
      fog: "Brouillard", hail: "Grêle", lightning: "Orage",
      "lightning-rainy": "Orage pluvieux", partlycloudy: "Partiellement nuageux",
      pouring: "Averses", rainy: "Pluvieux", snowy: "Neigeux",
      "snowy-rainy": "Neige et pluie", sunny: "Ensoleillé",
      windy: "Venteux", "windy-variant": "Venteux (variable)",
    },
    addMode: "Ajouter un mode",
    addCover: "Ajouter un volet",
    dragHint: "Dans l'ordre du sélecteur de mode : glisser une ligne pour le changer.",
    behaviorKind: { none: "Position fixe", auto_shade: "Suit l'ombrage", solar_gain: "Suit l'héliotropie" },
    backToModes: "Tous les modes",
    newMode: "Nouveau mode",
    name: "Nom",
    icon: "Icône",
    color: "Couleur",
    behaviorHint: "La matrice peut toujours imposer une position ou une entité à un volet.",
    lockField: "Verrouiller les volets",
    lockHint: "Les volets ne bougent plus ; les positions demandées sont gardées en mémoire.",
    hiddenField: "Masquer du sélecteur",
    hiddenHint: "Le mode reste utilisable par les automatisations.",
    entitiesSec: "Entités générées",
    entitiesSub: "Ce que cette configuration a produit dans Home Assistant.",
    entityKinds: {
      select: "Sélecteurs de mode", switch: "Interrupteurs",
      binary_sensor: "Capteurs binaires", sensor: "Capteurs",
    },
    entityTotal: (n) => `${n} entité${n > 1 ? "s" : ""} au total`,
    delete: "Supprimer",
    inUseTitle: (n) => `Utilisé par ${n} volet${n > 1 ? "s" : ""} : le retirer d'abord de ces volets dans la matrice.`,
    inUseItemTitle: (n) => (n > 1 ? `Utilisé par ${n} volets : les déplacer d'abord.` : "Utilisé par 1 volet : le déplacer d'abord."),
    backToCovers: "Tous les volets",
    entity: "Entité du volet",
    picture: "Image",
    exclusion: "Exclusions de sécurité",
    inhibition: "Inhibitions",
    priorityField: "Mode prioritaire",
    priorityHint: "Passe outre les pauses (invités, enfants…), jamais les sécurités (fenêtre ouverte, pluie).",
    priority: "prioritaire",
    durationField: "Durée limitée",
    durationHint: "Le volet quitte ce mode tout seul à la fin du délai.",
    durationLabel: "Durée",
    returnField: "À la fin du délai",
    returnBase: "revenir au mode précédent",
    returnHint: "Le mode précédent est le dernier mode sans durée dans lequel était le volet. Seuls les modes sans durée peuvent être choisis ici. Choisir un mode sans durée avant la fin arrête le décompte.",
    timedChip: (n, r) => (r ? `${n} min, puis ${r}` : `${n} min`),
    statusTimer: (m, t) => `retour à ${m} à ${t}`,
    statusLocked: (p) => (p == null ? "verrouillé" : `verrouillé, ${p} % mémorisé`),
    schedNext: "prochain", schedTomorrow: (t) => `demain ${t}`, schedNone: "rien",
    schedTitle: "Horaires", schedEdit: "Modifier",
    coverModesTitle: "Modes de ce volet", seeMatrix: "Voir la matrice",
    addPicture: "Ajouter une image",
    nav: { cover: "Volet", modes: "Modes", block: "Blocages", detection: "Soleil" },
    schedOpen: "Ouvrir l'onglet Horaires", schedAria: (n) => `Horaires de ${n}, ouvrir l'onglet Horaires`,
    fcSafety: (n) => `${n} : le volet bougera une fois l'exclusion levée.`,
    fcInhib: (n) => `${n} : le volet bougera à la fin de l'inhibition.`,
    fcMemory: (p) => `Verrouillé : ${p} % ira en mémoire, pris en quittant le mode.`,
    fcRecompute: "Son mode actuel calcule la position : le calcul suivant peut le rebouger.",
    fcSpared: (cur, m) => `${m} ne remplace pas ${cur} : le volet reste en ${cur}.`,
    fcAfterTimed: (cur, m) => `${m} s'appliquera à la fin de ${cur}.`,
    entitiesShow: "Voir les entités",
    groupedTitle: "Appliqué à plusieurs volets",
    groupedHint: "Sélecteur global, horaires, automatisations. Un choix fait sur le sélecteur d'un volet passe toujours.",
    groupedInfo: "L'action apply_mode avec force: true passe aussi.",
    sparesField: "Laisser tranquilles les volets en",
    sparesHint: "Un volet en mode minuté n'est pas dérangé non plus, et prend ce mode à la fin de son délai.",
    sparesNone: "Aucun mode : celui-ci remplace tous les autres.",
    sparesAdd: "+ mode",
    sparesChip: (names) => (names.length <= 2 ? `épargne ${names.join(", ")}` : `épargne ${names.length} modes`),
    fallbackChip: (m) => `sinon ${m}`,
    fallbackField: "Les volets sans ce mode dans la matrice passent en",
    fallbackHint: "Ex. : Absence, puis Automatique sur les volets qui n'ont pas Absence.",
    fallbackNone: "rien (ils ne bougent pas)",
    usedAsReturn: (names) => `Ce mode est le mode de retour de ${names.map((n) => `« ${n} »`).join(", ")} : il ne peut pas avoir de durée tant qu'il l'est.`,
    noTemplateOpt: "Aucun gabarit",
    overrides: (n) => `${n} écart${n > 1 ? "s" : ""}`,
    revertTitle: "Revenir à la valeur du gabarit",
    sections: { geometry: "Géométrie", detection: "Détection", shading: "Ombrage", solar_gain: "Héliotropie" },
    fields: {
      angle_left: "Angle à gauche", angle_right: "Angle à droite",
      shade_distance: "Distance du volet", shade_max_height: "Hauteur maxi",
      shade_min_height: "Hauteur mini",
      shade_min_elevation: "Élévation mini", shade_max_elevation: "Élévation maxi",
      shade_minimum_position: "Position mini", shade_default_position: "Position par défaut",
      shade_change_threshold: "Seuil de changement", shade_time_out: "Temporisation",
      solar_gain_position_solar: "Position au soleil", solar_gain_position_cold: "Position au froid",
      shade_enable: "Ombrage automatique activé", solar_gain_enable: "Héliotropie activée",
      shade_sun_position: "Position quand le soleil tape",
    },
    fieldsRoof: { shade_max_height: "Longueur de la vitre", shade_min_height: "Longueur mini" },
    /* ---- éditeurs, présentation 4.0 ---- */
    inSelector: "Dans le sélecteur :",
    colorPick: "Choisir une couleur",
    colorHex: "Code hexadécimal de la couleur",
    behaviorTitle: "Position des volets",
    behaviorCardSub: "Comment ce mode choisit la position de chaque volet.",
    behaviorOpts: {
      none: ["Fixe", "réglée dans la matrice"],
      auto_shade: ["Ombrage", "suit le soleil"],
      solar_gain: ["Héliotropie", "laisse entrer le soleil"],
    },
    whileTitle: "Pendant ce mode",
    whileSub: "Tant que le volet est dans ce mode.",
    timedFor: "Pendant",
    timedThen: "min, puis",
    advanced: "Avancé",
    advSummary: (prio, hidden) => `${prio ? "prioritaire" : "non prioritaire"} · ${hidden ? "masqué" : "visible"}`,
    picturePh: "/local/… (facultatif)",
    blockTitle: "Ce qui bloque le volet",
    blockSub: "Ce qui a été demandé pendant le blocage s'applique quand l'entité retombe.",
    safetyTitle: "Sécurité : rien ne bouge",
    safetySub: "Même un mode prioritaire attend.",
    safetyEx: "Ex. : fenêtre ouverte, capteur de pluie.",
    pauseTitle: "Pause : Cover Extender n'y touche pas",
    pauseSub: "Un mode prioritaire passe quand même.",
    pauseEx: "Ex. : invités, enfants, un capteur template « mercredi matin ».",
    addEntity: "Ajouter une entité",
    removeEntity: "Retirer",
    calcTitle: "Calcul de la position",
    calcFrom: "Valeurs du gabarit",
    calcExcept: ", sauf",
    calcNoOwn: ", sans écart",
    noTplChip: "Sans gabarit : toutes les valeurs sont celles du volet.",
    openTemplate: "Ouvrir le gabarit",
    sectionTitles: {
      geometry: "Géométrie de la fenêtre", detection: "Quand le soleil fait face",
      shading: "Ombrage", solar_gain: "Héliotropie",
    },
    sectionSubs: {
      geometry: "Pour savoir jusqu'où le soleil entre dans la pièce.",
      detection: "Où doit être le soleil : un secteur pour tout, une plage de hauteur pour l'ombrage.",
      shading: "Le volet descend juste ce qu'il faut quand le soleil est devant.",
      solar_gain: "Laisser entrer le soleil quand il fait frais et beau. Température et météo : onglet Réglages.",
    },
    fieldHints: {
      shade_distance: "Jusqu'où la lumière directe peut entrer, au sol.",
      shade_max_height: "Bas du volet ouvert à 100 %.",
      shade_min_height: "Bas du volet fermé : 0 pour une porte-fenêtre.",
      angle_left: "Vers l'est pour une façade sud.",
      angle_right: "Vers l'ouest pour une façade sud.",
      shade_minimum_position: "L'ombrage ne ferme jamais plus que ça.",
      shade_default_position: "Quand le soleil n'est pas devant la fenêtre.",
      shade_change_threshold: "Les petits mouvements sont ignorés, pour ménager le moteur.",
      shade_time_out: "Attente après tout mouvement du volet, manuel compris.",
      solar_gain_position_solar: "Frais, beau temps, soleil devant.",
      solar_gain_position_cold: "Frais, mais pas de soleil sur la fenêtre ou mauvais temps.",
      shade_sun_position: "Fenêtres à plat seulement : le soleil tombe droit dans la pièce, le volet prend cette position tant que le soleil touche la vitre.",
    },
    fieldHintsRoof: {
      shade_distance: "Jusqu'où la lumière directe peut entrer, mesurée au niveau du bas de la vitre.",
      shade_max_height: "Le long de la pente, du bas au haut du vitrage (volet ouvert, 100 %).",
      shade_min_height: "Volet fermé : 0 pour la plupart des fenêtres de toit.",
    },
    fromTemplate: (v) => `gabarit : ${v}`,
    ovrLabel: "Écart",
    backToTpl: "Revenir au gabarit",
    inheritedTitle: (n) => `Valeur du gabarit ${n} : la modifier crée un écart sur ce volet.`,
    filterAll: "Tout",
    filterOwn: (n) => `Écarts seulement (${n})`,
    noOwn: "Aucun écart : ce volet suit son gabarit partout.",
    elevationRange: "Hauteur du soleil",
    elevationHint: "En dehors, le volet va à sa position par défaut.",
    elevationHintRoof: "Se lit depuis l'horizon devant, par-dessus le zénith (90°), jusqu'au toit : 120° vaut 60° de dos.",
    elevEnds: ["horizon, devant", "zénith", "le toit, de dos"],
    rangeTo: "à",
    fig: {
      outside: "dehors", room: "pièce", max: "haut. maxi", min: "haut. mini",
      distance: "distance", left: "gauche", right: "droite", view: "vu de l'intérieur",
      top: "vue de dessus", side: "de profil", section: "en coupe", horizon: "horizon",
      sectorSun: "héliotropie, capteur et ombrage", sectorShade: "hauteur pour l'ombrage", sunNow: "le soleil maintenant",
      behindRoof: "derrière : seulement au-dessus du toit", wholeSky: "tout le ciel, toutes directions", behind: "de dos",
      length: "longueur",
    },
    detGroupSun: "Héliotropie, capteur « face au soleil » et ombrage",
    detGroupShade: "Ombrage",
    tplName: "Nom du gabarit",
    usedBy: "Utilisé par",
    noCoverYet: "Aucun volet pour l'instant",
    tplFacades: (list) => `Façades de ce type : ${list}.`,
    tplNoFacade: "Aucune façade de ce type pour l'instant.",
    facadeName: "Nom de la façade",
    facadeCovers: "Volets sur cette façade",
    orientTitle: "Orientation",
    orientSub: "Vers où regardent les fenêtres, vu de l'intérieur.",
    dragCompass: "ou faire tourner la boussole",
    compassNote: "La fenêtre est en haut, vue de l'intérieur : les lettres tournent autour de la maison, la flèche ne bouge pas. Le jaune montre d'où le soleil peut faire face à la façade.",
    compassLeft: "à gauche",
    sectorRange: "Secteur",
    sectorHint: "Où le soleil compte comme devant la fenêtre, de part et d'autre de son axe.",
    sectorEnds: ["← gauche", "axe de la fenêtre", "droite →"],
    compassRight: "à droite",
    slopeTitle: "Pente",
    slopeSub: "L'angle de la vitre avec l'horizontale.",
    slopeKinds: { wall: "Mur", roof: "Toit", flat: "À plat" },
    kindNoun: { wall: "un mur", roof: "un toit", flat: "une fenêtre à plat" },
    tplKind: "Pour les fenêtres",
    tplKindRef: (t, house) => `Dessiné sur un toit à ${t}°${house ? ", le moins pentu des toits de la maison" : ""}.`,
    tplKindMismatch: (t, tk, fk) => `Le gabarit « ${t} » est prévu pour ${tk}, pas pour ${fk} : en choisir un autre, ou aucun.`,
    tplKindUsers: (list) => `Des volets qui l'utilisent sont sur une façade d'un autre type : ${list}. L'enregistrement sera refusé.`,
    facadeKindUsers: (list) => `Ces volets ont un gabarit d'un autre type de fenêtre : ${list}. Changer d'abord leur gabarit.`,
    facadeDir: "Vers où regarde la fenêtre",
    slopeAria: "Pente, en degrés",
    slopeNotes: {
      wall: "Une fenêtre droite ne voit que le ciel devant elle. Toit et À plat laissent aussi venir le soleil de derrière ; une fenêtre de toit se règle par la longueur de sa vitre au lieu des hauteurs, une fenêtre à plat par une position au soleil.",
      roof: "Une fenêtre de toit voit aussi une partie du ciel derrière elle : le soleil touche la vitre dès qu'il est plus haut que la pente.",
      flat: "Un puits de lumière à plat voit tout le ciel : le soleil le touche dès qu'il est levé, quelle que soit sa direction. L'azimut ne sert plus.",
    },
    slopeShort: (t) => (t >= 90 ? "" : t < 10 ? "à plat" : `toit ${t}°`),
    dirs: ["N", "NE", "E", "SE", "S", "SO", "O", "NO"],
    addShort: "Ajouter",
    tplMeta: (kind, h, d) => (kind === "flat" ? "à plat" : `${kind === "roof" ? "toit · longueur" : "hauteur"} ${h} m · distance ${d} m`),
    sgTitle: "Héliotropie",
    sgSub: "Quand fait-il assez frais et beau pour laisser entrer le soleil ? Vaut pour tous les volets.",
    sgThreshold: "Seuil",
    sgThrValue: "Valeur",
    sgThrEntity: "Entité",
    sgCoolWhen: "Il fait frais quand",
    sgIsBelow: "est sous",
    sgFineWhen: "Il fait beau quand",
    sgReports: "annonce :",
    sgMore: (n) => `+ ${n} autres`,
    sgLess: "Replier",
    sgNote: "Sans température, le premier test est ignoré ; sans météo, il fait toujours beau.",
    sgTooWarm: (t, s) => `${t} ≥ ${s} : trop chaud, l'héliotropie attend`,
    sgCool: (t, s) => `${t} < ${s} : assez frais`,
    cmdTitle: "Envoi des commandes",
    extraTitle: "Entités en plus, pour chaque volet",
    extraSub: "Pour vos tableaux de bord et automatisations.",
    showHints: {
      sun_facing: "Capteur binaire : le soleil fait-il face au volet ?",
      auto_shade: "Capteur binaire : l'ombrage est-il activé sur ce volet ?",
      solar_gain: "Capteur binaire : l'héliotropie est-elle activée sur ce volet ?",
    },
    unsaved: "Modifications non enregistrées",
    errors: {
      name_required: () => "Le nom ne peut pas être vide.",
      name_exists: (n) => `Le nom « ${n} » existe déjà.`,
      behavior_invalid: (n) => `Comportement invalide pour « ${n} ».`,
      color_invalid: (n) => `Couleur invalide pour « ${n} ».`,
      duration_invalid: (n) => `Durée de « ${n} » : entre 1 et 1440 minutes.`,
      return_mode_invalid: (n) => `« ${n} » : le mode de retour doit être un mode existant sans durée.`,
      fallback_invalid: (n) => `« ${n} » : le mode de repli doit être un autre mode existant.`,
      schedule_mode_timed: (m) => `« ${m} » est appliqué par un horaire : il ne peut pas avoir de durée, et un mode avec une durée ne peut pas être programmé.`,
      schedule_invalid: (k) => `L'horaire « ${k} » est illisible.`,
      schedule_position_invalid: (e) => `${e} : une position programmée va de 0 à 100 %.`,
      schedule_min_after_max: (k) => `Horaire « ${k} » : l'heure min est après l'heure max.`,
      schedule_floor_after_ceiling: (k) => `Horaire « ${k} » : « pas avant » doit précéder « pas après ».`,
      return_mode_timed: (target, user) => `« ${target} » est le mode de retour de « ${user} » : il ne peut pas avoir de durée. Changez d'abord le retour de « ${user} ».`,
      in_use: (n, count, covers) => `« ${n} » est encore utilisé par ${count} volet${Number(count) > 1 ? "s" : ""} : ${covers}`,
      entity_required: () => "Un volet doit désigner une entité.",
      cover_domain: (e) => `${e} n'est pas une entité du domaine cover.`,
      cover_exists: (e) => `Le volet ${e} figure déjà dans la liste.`,
      picture_invalid: (e) =>
        `${e} : l'image doit être un chemin local (ex. /local/mon-image.png), pas une URL externe.`,
      facade_required: (e) => `${e} : façade manquante ou inconnue.`,
      template_unknown: (t) => `Gabarit inconnu : ${t}`,
      mode_unknown: (m) => `Mode inconnu : ${m}`,
      modes_invalid: (e) => `${e} : la carte des modes est illisible.`,
      mode_cfg_invalid: (m) => `Configuration illisible pour le mode ${m}.`,
      position_out_of_range: (m) => `Position hors bornes pour le mode ${m}.`,
      mode_entity_required: (m) => `Le mode ${m} attend une entité.`,
      min_height_above_max: (e) => `${e} : la hauteur mini dépasse la maxi.`,
      min_elevation_above_max: (e) => `${e} : l'élévation mini dépasse la maxi.`,
      azimuth_invalid: (n) => `Azimut invalide pour « ${n} » (0 à 360°).`,
      tilt_invalid: (n) => `Pente invalide pour « ${n} » (0 à 90°).`,
      window_kind_invalid: (n) => `Type de fenêtre invalide pour « ${n} ».`,
      window_kind_mismatch: (e, t, f) => `${e} : le gabarit « ${t} » et la façade « ${f} » ne sont pas du même type de fenêtre (mur, toit ou à plat).`,
      field_invalid: (f) => `Valeur illisible pour « ${f} ».`,
      interval_invalid: () => "L'intervalle doit être compris entre 0 et 5000 ms.",
      conditions_invalid: () => "Liste de conditions météo illisible.",
      condition_unknown: (c) => `Condition météo inconnue : ${c}`,
    },
  },
};

/* Icons are not words: they said the same thing in every table, and a table is
   the one place where a duplicated value drifts. They live here instead. */
const SECTION_ICONS = {
  geometry: "mdi:ruler-square", detection: "mdi:sun-compass",
  shading: "mdi:weather-sunny", solar_gain: "mdi:thermometer",
};

/* The weather states as the "fine weather" chips draw them. */
const WEATHER_ICONS = {
  "clear-night": "mdi:weather-night", cloudy: "mdi:weather-cloudy",
  exceptional: "mdi:alert-circle-outline", fog: "mdi:weather-fog", hail: "mdi:weather-hail",
  lightning: "mdi:weather-lightning", "lightning-rainy": "mdi:weather-lightning-rainy",
  partlycloudy: "mdi:weather-partly-cloudy", pouring: "mdi:weather-pouring",
  rainy: "mdi:weather-rainy", snowy: "mdi:weather-snowy", "snowy-rainy": "mdi:weather-snowy-rainy",
  sunny: "mdi:weather-sunny", windy: "mdi:weather-windy", "windy-variant": "mdi:weather-windy-variant",
};

/** "fr-CA" has no table of its own; its base language has one, and that is the answer. */
function pickLanguage(want) {
  const asked = String(want || "en");
  const base = asked.split("-")[0].split("_")[0];
  return WORDS[asked] ? asked : WORDS[base] ? base : "en";
}

/** English, overlaid with whatever the chosen language actually translated. */
function mergeWords(base, over) {
  const out = { ...base };
  for (const [key, value] of Object.entries(over || {})) {
    const under = out[key];
    // Plain objects merge; strings, functions and arrays replace. `typeof fn`
    // is "function", never "object", so a translated function is never walked
    // into; an array is an "object", and merging one would turn it into a
    // keyed object that no longer destructures or maps.
    const plain = (v) => v && typeof v === "object" && !Array.isArray(v);
    out[key] = plain(value) && plain(under) ? mergeWords(under, value) : value;
  }
  return out;
}

/* Guessed at load time from the page, because the shell can draw before any
   hass has arrived; confirmed by `set hass`, which carries the reader's own
   choice rather than their browser's. */
let LANG = pickLanguage(
  (typeof document !== "undefined" && document.documentElement?.lang) ||
    (typeof navigator !== "undefined" && navigator.language)
);
let T = mergeWords(WORDS.en, WORDS[LANG]);

/** Adopt the reader's language. True when it changed and the page must be redrawn. */
function setLanguage(hass) {
  const next = pickLanguage(hass?.locale?.language || hass?.language || LANG);
  if (next === LANG) return false;
  LANG = next;
  T = mergeWords(WORDS.en, WORDS[LANG]);
  return true;
}

/* ---------- ha-form / ha-selector loader (same trick as tyre_tracker) ---------- */
let formLoading = null;
function loadHaForm() {
  if (customElements.get("ha-selector")) return Promise.resolve();
  if (!formLoading) {
    formLoading = (async () => {
      const helpers = await window.loadCardHelpers?.();
      const card = await helpers?.createCardElement?.({ type: "entities", entities: [] });
      await card?.constructor?.getConfigElement?.();
    })().catch(() => {});
  }
  return formLoading;
}

/* ---------- tiny DOM helpers ---------- */
function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

function icon(name, cls = "") {
  const i = document.createElement("ha-icon");
  i.setAttribute("icon", name);
  if (cls) i.className = cls;
  return i;
}

function toast(node, message) {
  node.dispatchEvent(new CustomEvent("hass-notification", {
    detail: { message }, bubbles: true, composed: true,
  }));
}

/* ---------- mode config helpers (mirror of the flow's _mode_cfg_* ) ---------- */
function cfgKind(cfg) {
  if (!cfg || typeof cfg !== "object") return "none";
  if (cfg.type === "fixed") return "fixed";
  if (cfg.type === "entity" && cfg.value) return "entity";
  return "none"; // "auto" in storage
}

/* ---------- the three behaviours an "auto" cell can stand for ----------
 *
 * The plate colour belongs to the BEHAVIOUR and never to the mode. The cell
 * background already carries the mode's own colour, so an icon that took its
 * hue from the same place could no longer say which of the three computations
 * applies — the very thing it is there for: the same mdi:refresh-auto glyph
 * would read grey on Automatique, green on Manuel and pink on Invités.
 *
 * Warm = a position is being computed (by the sun, by the temperature).
 * Grey  = no instruction at all; the cover simply stays where it is.
 * The plate is opaque so the mode tint behind it cannot wash it out.
 */
const BEHAVIORS = {
  auto_shade: { icon: "mdi:weather-sunny", color: "var(--ce-b-shade)" },
  solar_gain: { icon: "mdi:thermometer",   color: "var(--ce-b-gain)" },
  none:       { icon: "mdi:refresh-auto",  color: "var(--ce-b-none)" },
};

function behaviorBadge(behavior) {
  const key = BEHAVIORS[behavior] ? behavior : "none";
  const spec = BEHAVIORS[key];
  const plate = el("span", "bico");
  plate.style.color = spec.color;
  plate.style.borderColor = `color-mix(in srgb, ${spec.color} 45%, transparent)`;
  plate.title = T.legendBehavior[key];
  plate.append(icon(spec.icon));
  return plate;
}

/* ---------- orientation: one convention for every drawing ----------
 * Azimuths are degrees from north, clockwise. On screen, angles are measured
 * from straight up, clockwise, like a compass; every view puts the window at
 * the bottom looking up (seen from inside), so "left" on screen is the left of
 * someone looking out of the window. */
const toRad = (deg) => (deg * Math.PI) / 180;
const wrap360 = (deg) => ((deg % 360) + 360) % 360;
const wrap180 = (deg) => wrap360(deg + 180) - 180;

/** A facade's azimuth; 180 (south) when it has none, as the server assumes. */
const facadeAzimuth = (facade) => Number(facade?.azimuth ?? 180);

/* ---------- slopes: walls, roof windows, flat skylights ----------
 * A facade's tilt is the glass's angle with the horizontal: 90 for a wall
 * (and every facade saved without one), 30 for a window in a 30° roof, 0 for
 * a flat skylight. The same rules as shade.py on the server. */
const FLAT_TILT = 10;
const facadeTilt = (facade) => Number(facade?.tilt ?? 90);
/** "wall", "roof" or "flat": the three shapes the panel draws and words apart. */
const tiltKind = (tilt) => (tilt >= 90 ? "wall" : tilt < FLAT_TILT ? "flat" : "roof");
/** Where the heights stop: at the zenith on a wall or a flat window; on a roof,
 *  down the far side to the roof itself. */
/**
 * Where to put the glass of a sloped profile, and how big its cone can be,
 * so the drawing fills its 150 × 150 box. The cone is centred on the glass,
 * opens over *ranges* of heights (0 in front, 90 the zenith, 180 behind) and
 * keeps 8 around for its labels; the glass (*G* long, along *up*), its angle
 * label on a roof and the horizon label under it keep their own size. The
 * largest radius that fits wins, its cone centred in the room left.
 */
function profileFit(ranges, up, G, roof) {
  const hs = ranges.flatMap(([a, b]) => {
    const out = [a, b];
    for (let h = Math.ceil(a / 10) * 10; h < b; h += 10) out.push(h);
    return out;
  });
  const ux = hs.map((h) => Math.cos(toRad(h))), uy = hs.map((h) => -Math.sin(toRad(h)));
  const ux0 = Math.min(0, ...ux), ux1 = Math.max(0, ...ux), uy0 = Math.min(0, ...uy);
  const half = G / 2;
  // The glass and its words, from the cone's centre.
  const fixL = Math.min(up[0] * half, -up[0] * half) - (roof ? 41 : 0);
  const fixR = Math.max(up[0] * half, -up[0] * half);
  const fixB = -up[1] * half + 15;
  for (let r = 115; r > 30; r -= 1) {
    const xlo = Math.max(14 - r * ux0, 6 - fixL), xhi = Math.min(136 - r * ux1, 144 - fixR);
    const ylo = 16 - r * uy0, yhi = 146 - fixB;
    if (xlo <= xhi && ylo <= yhi) return [[(xlo + xhi) / 2, (ylo + yhi) / 2], r];
  }
  return [[75, 100], 30];
}

/** The window type a template is for; one saved before types existed is a wall's. */
const templateKind = (tpl) => (["roof", "flat"].includes(tpl?.kind) ? tpl.kind : "wall");
const heightLimit = (tilt) => (tiltKind(tilt) === "roof" ? 180 - tilt : 90);
/** Whether a sun `off` degrees from the window's axis and `el` high is on the
 *  outer side of the glass (the sign of the cosine of incidence). */
const sunOnGlass = (off, el, tilt) =>
  Math.sin(toRad(el)) * Math.cos(toRad(tilt)) + Math.cos(toRad(el)) * Math.sin(toRad(tilt)) * Math.cos(toRad(off)) >= -1e-9;

/** The nearest of the eight directions to an azimuth, in the reader's language. */
const dirName = (azimuth) => T.dirs[Math.round(wrap360(azimuth) / 45) % 8];

/** The point at screen angle `deg`, distance `r` from (cx, cy). */
const polar = (cx, cy, deg, r) => [cx + r * Math.sin(toRad(deg)), cy - r * Math.cos(toRad(deg))];

/** Where a ray leaving (x0, y0) at screen angle `deg` meets the circle of radius
 *  `r` around (cx, cy): how a sector drawn from a window's edges keeps a true arc. */
function rayToCircle(x0, y0, cx, cy, deg, r) {
  const dx = Math.sin(toRad(deg)), dy = -Math.cos(toRad(deg)), ox = x0 - cx, oy = y0 - cy;
  const b = ox * dx + oy * dy;
  const t = -b + Math.sqrt(b * b - (ox * ox + oy * oy - r * r));
  return [x0 + t * dx, y0 + t * dy];
}

/** The sun seen from a window facing `azimuth`: its angle from the window's axis
 *  (negative = to the left) and its height. Null while it is down or unknown. */
function sunFromFacade(hass, azimuth) {
  const sun = hass?.states?.["sun.sun"]?.attributes;
  if (!sun || !(Number(sun.elevation) > 0)) return null;
  return { off: wrap180(Number(sun.azimuth) - azimuth), el: Number(sun.elevation) };
}

/** The way a facade's windows look, on a map with north up: down for south.
 *  A flat skylight looks nowhere in particular: a plain compass. */
function facadeArrow(facade, cls = "round az") {
  const badge = el("span", cls);
  badge.title = T.facadeDir;
  if (tiltKind(facadeTilt(facade)) === "flat") {
    badge.append(icon("mdi:compass-outline"));
    return badge;
  }
  const arrow = icon("mdi:arrow-up");
  arrow.style.transform = `rotate(${facadeAzimuth(facade)}deg)`;
  badge.append(arrow);
  return badge;
}

/** A slider's fill, drawn by the page's own CSS (--p) rather than the browser:
 *  one look on every engine, a light track and the colour on the fill only. */
function paintRange(range) {
  const min = Number(range.min) || 0, max = Number(range.max) || 100;
  range.style.setProperty("--p", `${((Number(range.value) - min) / ((max - min) || 1)) * 100}%`);
}

/* ---------- error helper ---------- */
/** Turn a server error code ("in_use:Ombre:3:cover.a") into a sentence. */
function wsError(err) {
  const raw = String(err?.message || err?.code || "");
  const [code, ...rest] = raw.split(":");
  const fn = T.errors[code];
  return fn ? fn(...rest) : T.rawError(raw);
}

const FONTS = `
:host {
  --f-base: calc(var(--ha-font-size-s, 14px) * 15 / 14);
  --f-9-5:  calc(var(--f-base) *  9.5 / 14);
  --f-10:   calc(var(--f-base) * 10   / 14);
  --f-10-5: calc(var(--f-base) * 10.5 / 14);
  --f-11:   calc(var(--f-base) * 11   / 14);
  --f-11-5: calc(var(--f-base) * 11.5 / 14);
  --f-12:   calc(var(--f-base) * 12   / 14);
  --f-12-5: calc(var(--f-base) * 12.5 / 14);
  --f-13:   calc(var(--f-base) * 13   / 14);
  --f-14:   var(--f-base);
  --f-15:   calc(var(--f-base) * 15   / 14);
  --f-16:   calc(var(--f-base) * 16   / 14);
  --f-17:   calc(var(--f-base) * 17   / 14);
  --f-20:   calc(var(--f-base) * 20   / 14);
  --f-24:   calc(var(--f-base) * 24   / 14);
  --f-34:   calc(var(--f-base) * 34   / 14);
}
`;

const CONTROLS = `
:host {
  --fp-ok:   var(--success-color, #3E9D6B);
  --fp-warn: var(--warning-color, #B38046);
  --fp-bad:  var(--error-color, #FF554C);
  --fp-info: var(--info-color, #039be5);

  --fp-focus: 2px solid var(--primary-color, #03a9f4);
  --fp-focus-off: 2px;

  --fp-s0: 2px;
  --fp-s1: 4px;
  --fp-sh: 6px;
  --fp-s2: 8px;
  --fp-s3: 12px;
  --fp-s4: 16px;
  --fp-s5: 24px;

  --fp-pill-h: 30px;
  --fp-pill-r: 15px;
  --fp-ctl-h: 40px;
  --fp-ctl-r: 8px;
  --fp-field-r: 4px;
  --fp-round: 40px;
  --fp-round-lg: 48px;

  /* The behaviour family. One saturation, one lightness, the hue alone moves —
     that is what makes the three read as one set instead of three borrowed
     tokens. --fp-warn and --fp-bad were an alert palette (warning, error) and
     carried the wrong meaning as much as the wrong shade; the third was not a
     colour at all but the text token pressed into service as a plate.
     Cold for the passive case, warm for the two computed ones. */
  --ce-beh-s: 72%;
  --ce-beh-l: 54%;
  --ce-b-none:  hsl(205 var(--ce-beh-s) var(--ce-beh-l));
  --ce-b-shade: hsl(40  var(--ce-beh-s) var(--ce-beh-l));
  --ce-b-gain:  hsl(348 var(--ce-beh-s) var(--ce-beh-l));

  /* Schedule editor: the max / min handles, the crossings, the floor and
     ceiling, and the band where the cover is closed before sunset (or open
     before sunrise). */
  --ce-h:      hsl(250 45% 56%);
  --ce-x:      hsl(155 55% 38%);
  --ce-clamp:  hsl(335 48% 52%);
  --ce-band:   hsl(20 85% 55% / .13);
}
`;

const STYLE = `
  ${FONTS}
  ${CONTROLS}
  :host {
    display: block;
    height: 100vh;
    overflow: auto;
    background: var(--primary-background-color);
    color: var(--primary-text-color);
    -webkit-font-smoothing: antialiased;
    font-size: var(--f-14);
  }
  * { box-sizing: border-box; }
  .wrap { max-width: 1400px; margin: 0 auto; padding: var(--fp-s4) var(--fp-s4) calc(var(--fp-s5) * 2); }

  header.bar {
    display: flex; align-items: center; gap: var(--fp-s3); flex-wrap: wrap;
    padding: var(--fp-s2) var(--fp-s1) var(--fp-s4);
  }
  .logo {
    width: var(--fp-ctl-h); height: var(--fp-ctl-h); border-radius: var(--fp-ctl-r); flex: none;
    background: var(--primary-color); color: var(--text-primary-color, #fff);
    display: flex; align-items: center; justify-content: center;
  }
  .logo ha-icon { --mdc-icon-size: 22px; width: 22px; height: 22px; }
  .title { font-size: var(--f-17); font-weight: 600; }
  .ver { font-size: var(--f-11); color: var(--secondary-text-color); }
  .tabs {
    margin-left: auto; display: flex; gap: var(--fp-s0); padding: var(--fp-s1);
    background: var(--secondary-background-color); border-radius: var(--fp-ctl-r);
  }
  .tab {
    border: 0; background: transparent; color: var(--secondary-text-color);
    font: inherit; font-size: var(--f-13); font-weight: 500;
    height: var(--fp-pill-h); padding: 0 var(--fp-s4);
    border-radius: var(--fp-field-r); cursor: pointer;
  }
  .tab[aria-selected="true"] {
    background: var(--card-background-color); color: var(--primary-text-color);
    font-weight: 600; box-shadow: 0 1px 3px rgba(0,0,0,.2);
  }
  .tab-sep { width: 1px; flex: none; align-self: stretch; margin: var(--fp-s1); background: var(--divider-color); }
  /* The tab holding unsaved changes. */
  .tab.dirty::after { content: ""; display: inline-block; width: 6px; height: 6px; border-radius: 50%;
                      margin-left: var(--fp-sh); vertical-align: middle; background: var(--fp-warn); }
  .tab:focus-visible, button:focus-visible, .cv:focus-visible {
    outline: var(--fp-focus); outline-offset: var(--fp-focus-off);
  }

  .note {
    font-size: var(--f-12-5); color: var(--secondary-text-color);
    background: var(--secondary-background-color);
    border-radius: var(--fp-ctl-r); padding: var(--fp-s2) var(--fp-s3); margin: 0 0 var(--fp-s4);
  }
  .center { padding: calc(var(--fp-s5) * 3) var(--fp-s5); text-align: center; color: var(--secondary-text-color); }

  .card {
    background: var(--card-background-color);
    border-radius: var(--ha-card-border-radius, 12px);
    border: 1px solid var(--divider-color);
    padding: var(--fp-s4);
  }

  /* ---------- matrix ---------- */
  .m-tools { display: flex; align-items: center; gap: var(--fp-s2) var(--fp-s4); flex-wrap: wrap; margin: 0 0 var(--fp-s3); }
  .m-hint { flex: 1 1 340px; display: flex; align-items: center; gap: var(--fp-sh); margin: 0;
            font-size: var(--f-12-5); color: var(--secondary-text-color); }
  .m-hint ha-icon { --mdc-icon-size: 16px; width: 16px; height: 16px; flex: none; }
  .legend { display: flex; gap: var(--fp-s4); margin-left: auto; font-size: var(--f-12);
            color: var(--secondary-text-color); flex-wrap: wrap; }
  .legend span { display: inline-flex; align-items: center; gap: var(--fp-sh); }
  .legend ha-icon { --mdc-icon-size: 15px; width: 15px; height: 15px; }
  .lg { width: 22px; height: 15px; border-radius: var(--fp-field-r); display: inline-block; }
  .lg.fixed { background: var(--secondary-background-color); border: 1px solid var(--divider-color); }

  .m-scroll { overflow: auto; border: 1px solid var(--divider-color);
              border-radius: var(--ha-card-border-radius, 12px); position: relative;
              background: var(--card-background-color); max-height: calc(100vh - 190px); }
  table.matrix { border-collapse: separate; border-spacing: 0; min-width: 100%; width: max-content;
                 font-variant-numeric: tabular-nums; }
  .matrix th, .matrix td { padding: 0; }
  .matrix thead th { position: sticky; top: 0; z-index: 2; background: var(--card-background-color);
                     border-bottom: 1px solid var(--divider-color); }
  .matrix tbody th { position: sticky; left: 0; z-index: 1; background: var(--card-background-color);
                     border-right: 1px solid var(--divider-color); text-align: left; font-weight: normal; }
  .matrix thead th.corner { left: 0; z-index: 3; }
  .mh { display: flex; flex-direction: column; align-items: center; gap: var(--fp-s1); width: 100%;
        padding: var(--fp-s3) var(--fp-s2) var(--fp-sh); border: 0; background: none; font: inherit; cursor: pointer;
        min-width: 76px; font-weight: 500; font-size: var(--f-11-5); color: var(--secondary-text-color); }
  .mh:hover { color: var(--primary-text-color); }
  .mh .mico { width: 27px; height: 27px; border-radius: var(--fp-ctl-r);
              display: flex; align-items: center; justify-content: center; }
  .mh .mico ha-icon { --mdc-icon-size: 16px; width: 16px; height: 16px; }
  /* What sets the mode apart, in words, under its name. */
  .mh .tags { min-height: 13px; font-size: var(--f-10-5); font-weight: 400; white-space: nowrap;
              color: var(--secondary-text-color); }
  .rowh { display: flex; align-items: center; gap: var(--fp-s3);
          padding: var(--fp-s1) var(--fp-s4) var(--fp-s1) var(--fp-s3); min-width: 180px; }
  .rowh img, .rowh .pic { width: var(--fp-pill-h); height: var(--fp-pill-h);
                          border-radius: var(--fp-ctl-r); object-fit: cover; flex: none; }
  .rowh .pic { background: var(--secondary-background-color); border: 1px solid var(--divider-color);
               display: flex; align-items: center; justify-content: center; color: var(--secondary-text-color); }
  .rowh .pic ha-icon { --mdc-icon-size: 16px; width: 16px; height: 16px; }
  .rowh .nm { font-weight: 600; font-size: var(--f-13); line-height: 1.25; }
  tr.facade th, tr.facade td { background: var(--secondary-background-color) !important; }
  tr.facade .fl { display: flex; align-items: center; gap: var(--fp-sh); padding: var(--fp-s1) var(--fp-s3);
                  font-size: var(--f-11); font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
                  color: var(--secondary-text-color); }
  tr.facade .fl ha-icon { --mdc-icon-size: 13px; width: 13px; height: 13px; }
  .cell { padding: var(--fp-s1); }
  .cv { height: 34px; min-width: 70px; border-radius: var(--fp-ctl-r); display: flex; align-items: center;
        justify-content: center; gap: var(--fp-s1); font-size: var(--f-12-5); font-weight: 600; cursor: pointer;
        border: 1px solid transparent; color: var(--primary-text-color); }
  .cv:hover { border-color: var(--primary-color); }
  .cv.fixed { background: var(--secondary-background-color); border-color: var(--divider-color); }
  .cv.fixed:hover { border-color: var(--primary-color); }
  /* Background and icon colour are set inline from the mode's own colour. */
  .cv.auto { color: var(--primary-text-color); }
  /* Opaque, so the mode tint behind the cell cannot wash the glyph out, and
     bordered in its own hue so the plate still reads as a coloured object. */
  .bico { width: 20px; height: 20px; border-radius: var(--fp-field-r); flex: none;
          display: inline-flex; align-items: center; justify-content: center;
          background: var(--card-background-color); border: 1px solid transparent; }
  .bico ha-icon { --mdc-icon-size: 14px; width: 14px; height: 14px; }
  .cv.entity { background: color-mix(in srgb, var(--fp-warn) 16%, transparent); font-size: var(--f-11); }
  .cv.entity ha-icon { --mdc-icon-size: 13px; width: 13px; height: 13px; }
  /* An empty cell is a quiet dot; under the pointer or the focus it offers
     to add the mode. */
  .cv.empty { color: var(--primary-color); }
  .cv.empty::before { content: ""; width: 4px; height: 4px; border-radius: 50%; background: var(--divider-color); }
  .cv.empty ha-icon { display: none; --mdc-icon-size: 14px; width: 14px; height: 14px; }
  .cv.empty:hover, .cv.empty:focus-visible { border: 1px dashed var(--primary-color); }
  .cv.empty:hover::before, .cv.empty:focus-visible::before { display: none; }
  .cv.empty:hover ha-icon, .cv.empty:focus-visible ha-icon { display: inline-block; }
  /* A fixed position or an entity in a mode that computes: an override. */
  .cv.ovr { box-shadow: inset 0 0 0 1px var(--fp-warn); }
  /* The phone view: the covers one under the other, their modes two by two. */
  .seg.m-view { display: none; margin: 0; flex: none; }
  .seg.m-view button { flex: none; padding: 0 var(--fp-s3); }
  .m-list { display: none; gap: var(--fp-s2); }
  .m-list .grp-h { margin: var(--fp-s2) var(--fp-s1) 0; }
  .m-card { padding: var(--fp-s3); }
  .m-card > .nm { font-weight: 600; font-size: var(--f-14); margin-bottom: var(--fp-s2); }
  .m-cells { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--fp-s2); }
  .m-item { display: grid; gap: var(--fp-s0); min-width: 0; }
  .m-lab { display: flex; align-items: center; gap: var(--fp-sh); min-width: 0; font-size: var(--f-11-5);
           color: var(--secondary-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .m-item .cv { min-width: 0; }
  .m-cells .cv.empty { border: 1px dashed var(--divider-color); color: var(--secondary-text-color); }
  .m-cells .cv.empty::before { display: none; }
  .m-cells .cv.empty ha-icon { display: inline-block; }
  @media (max-width: 600px) {
    .seg.m-view { display: flex; }
    .m-box:not(.as-table) .m-scroll { display: none; }
    .m-box:not(.as-table) .m-list { display: grid; }
  }
  .gauge { width: 26px; height: 5px; border-radius: var(--fp-field-r); background: var(--divider-color);
           overflow: hidden; flex: none; }
  .gauge i { display: block; height: 100%; background: var(--primary-color); }
  .pct { color: var(--secondary-text-color); font-weight: 500; font-size: var(--f-10-5); }

  /* ---------- popover ---------- */
  .backdrop { position: fixed; inset: 0; z-index: 8; }
  /* Fixed, not absolute: the popover lives OUTSIDE .m-scroll so it is never
     clipped by it and never grows its scroll area. Re-anchored on scroll. */
  .pop { position: fixed; z-index: 9; width: 320px; max-width: calc(100vw - 16px);
         background: var(--card-background-color);
         border: 1px solid var(--divider-color); border-radius: var(--ha-card-border-radius, 12px);
         padding: var(--fp-s4); box-shadow: 0 4px 24px rgba(0,0,0,.3);
         max-height: calc(100vh - 16px); overflow-y: auto; overscroll-behavior: contain; }
  .pop h4 { margin: 0 0 var(--fp-s0); font-size: var(--f-13); }
  .pop .sub { font-size: var(--f-12); color: var(--secondary-text-color); margin: 0 0 var(--fp-s3); }
  .seg { display: flex; background: var(--secondary-background-color); border-radius: var(--fp-ctl-r);
         padding: var(--fp-s1); gap: var(--fp-s0); margin-bottom: var(--fp-s3); }
  .seg button { flex: 1; border: 0; background: transparent; font: inherit; font-size: var(--f-12-5);
                font-weight: 500; color: var(--secondary-text-color); height: var(--fp-pill-h);
                border-radius: var(--fp-field-r); cursor: pointer; }
  .seg button.on { background: var(--card-background-color); color: var(--primary-text-color);
                   font-weight: 600; box-shadow: 0 1px 2px rgba(0,0,0,.2); }
  .pos-slider { display: flex; align-items: center; gap: var(--fp-s3); margin-bottom: var(--fp-s3); }
  .pos-slider input[type=range] { flex: 1; min-width: 0; }
  .pos-slider .val { font-weight: 700; font-size: var(--f-14); min-width: 44px; text-align: right;
                     font-variant-numeric: tabular-nums; }
  .hint { font-size: var(--f-11-5); color: var(--secondary-text-color); margin: 0 0 var(--fp-s3); }
  .apply-row { display: flex; align-items: flex-start; gap: var(--fp-s2); font-size: var(--f-12);
               color: var(--secondary-text-color); margin: 0 0 var(--fp-s3); cursor: pointer; }
  .apply-row input { margin: var(--fp-s0) 0 0; accent-color: var(--primary-color); }
  .pop .actions { display: flex; align-items: center; gap: var(--fp-s2); }
  .pop .actions .spacer { flex: 1; }
  .btn { display: inline-flex; align-items: center; justify-content: center; gap: var(--fp-sh);
         font: inherit; font-size: var(--f-13); font-weight: 600; border-radius: var(--fp-ctl-r);
         height: var(--fp-ctl-h); padding: 0 var(--fp-s4); cursor: pointer;
         border: 1px solid var(--divider-color); background: var(--card-background-color);
         color: var(--primary-text-color); }
  .btn.primary { background: var(--primary-color); border-color: var(--primary-color);
                 color: var(--text-primary-color, #fff); }
  .btn.ghost { border-color: transparent; color: var(--secondary-text-color); }
  .btn.danger { border-color: transparent; color: var(--fp-bad); padding-left: 0; }
  .btn ha-icon { --mdc-icon-size: 18px; width: 18px; height: 18px; }
  .pop .btn { white-space: nowrap; }
  .btn[disabled] { opacity: .5; cursor: default; }
  ha-selector { display: block; margin-bottom: var(--fp-s3); }

  /* ---------- read-only tabs ---------- */
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 270px), 1fr)); gap: var(--fp-s3); }
  /* Cover cards side by side keep each part on the same line: every card
     spans the same five rows of the grid (head, state, schedules, forecast,
     features), so a card without schedules leaves that row empty instead of
     moving its features up. */
  @supports (grid-template-rows: subgrid) {
    .grid.covers { row-gap: 0; }
    .grid.covers > .card { display: grid; grid-row: span 5; grid-template-rows: subgrid; row-gap: 0;
                           align-content: start; margin-bottom: var(--fp-s3); }
    .grid.covers > .card > .c-head { grid-row: 1; }
    .grid.covers > .card > .status { grid-row: 2; }
    .grid.covers > .card > .sched-row { grid-row: 3; }
    .grid.covers > .card > .sched-hint { grid-row: 4; }
    .grid.covers > .card > .feats { grid-row: 5; align-self: end; }
  }
  /* A list's title line: what it holds and how many, its Add on the right. */
  .list-head { margin-bottom: var(--fp-s2); }
  .list-head h2 { margin: 0; font-size: var(--f-16); font-weight: 600; }
  .list-head .hint { margin: 0; }
  /* The covers of one facade, under its name, as in the matrix. */
  .fgroups { display: flex; flex-wrap: wrap; gap: var(--fp-s2) var(--fp-s3); }
  .fgroup { flex: 1 1 calc(var(--n) * 290px + (var(--n) - 1) * var(--fp-s3)); min-width: 0; max-width: 100%; }
  .grp-h { display: flex; align-items: baseline; gap: var(--fp-s2); margin: var(--fp-s2) var(--fp-s1);
           font-size: var(--f-11); font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
           color: var(--secondary-text-color); }
  .grp-h .az { font-weight: 500; letter-spacing: 0; text-transform: none; }
  .c-head { display: flex; align-items: center; gap: var(--fp-s3); margin-bottom: var(--fp-s3); }
  .c-head img, .c-head .pic { width: 38px; height: 38px; border-radius: var(--fp-ctl-r);
                              object-fit: cover; flex: none; }
  .c-head .pic { background: var(--secondary-background-color); border: 1px solid var(--divider-color);
                 display: flex; align-items: center; justify-content: center; color: var(--secondary-text-color); }
  .c-head .pic ha-icon { --mdc-icon-size: 20px; width: 20px; height: 20px; }
  .c-head .nm { font-weight: 600; font-size: var(--f-14); line-height: 1.2; }
  .c-head .eid { font-size: var(--f-11); color: var(--secondary-text-color); font-family: monospace; }
  .c-head .meta { font-size: var(--f-11-5); color: var(--secondary-text-color); }
  .chips { display: flex; gap: var(--fp-sh); flex-wrap: wrap; margin-bottom: var(--fp-s3); }
  .chip { display: inline-flex; align-items: center; gap: var(--fp-s1); font-size: var(--f-12); font-weight: 500;
          border: 1px solid var(--divider-color); border-radius: var(--fp-pill-r);
          padding: var(--fp-s0) var(--fp-s2); color: var(--secondary-text-color); }
  .chip ha-icon { --mdc-icon-size: 13px; width: 13px; height: 13px; }
  /* What runs on its own on this cover, and its overrides: only what is on. */
  .feats { display: flex; flex-wrap: wrap; gap: var(--fp-sh); border-top: 1px solid var(--divider-color);
           padding-top: var(--fp-s2); }
  /* The modes, one row each in the selector's order: grip, icon, name and
     what it does, its chips, a chevron. */
  .mico { width: 38px; height: 38px; border-radius: var(--fp-ctl-r); flex: none;
          display: flex; align-items: center; justify-content: center; }
  .mico ha-icon { --mdc-icon-size: 20px; width: 20px; height: 20px; }
  .mlist { padding: 0; overflow: hidden; }
  .mrow { display: grid; grid-template-columns: 18px 38px minmax(140px, 1fr) auto 20px; gap: var(--fp-s3);
          align-items: center; padding: 10px var(--fp-s4); border-top: 1px solid var(--divider-color); cursor: pointer; }
  .mrow:first-child { border-top: 0; }
  .mrow:hover { background: color-mix(in srgb, var(--primary-color) 5%, transparent); }
  .mrow:focus-visible { outline: var(--fp-focus); outline-offset: -2px; }
  .mrow.drop { box-shadow: inset 0 2px 0 var(--primary-color); }
  .mrow.dragging { opacity: .45; }
  .mrow .grip { color: var(--secondary-text-color); cursor: grab; --mdc-icon-size: 18px; width: 18px; height: 18px; }
  .mrow .mnames { display: grid; min-width: 0; }
  .mrow .nm { font-weight: 600; font-size: var(--f-14); }
  .mrow .meta { font-size: var(--f-12); color: var(--secondary-text-color); }
  .mrow .chips { margin: 0; justify-content: flex-end; }
  .mrow .chev { color: var(--secondary-text-color); --mdc-icon-size: 20px; width: 20px; height: 20px; }
  @media (max-width: 600px) {
    .mrow { grid-template-columns: 18px 38px minmax(0, 1fr) 20px; }
    .mrow .chips { grid-column: 3; grid-row: 2; justify-content: flex-start; }
    .mrow .chev { grid-column: 4; grid-row: 1; }
  }
  .mini { font-size: var(--f-10-5); font-weight: 600; text-transform: uppercase; letter-spacing: .04em;
          border-radius: var(--fp-field-r); padding: var(--fp-s0) var(--fp-sh);
          background: var(--secondary-background-color); color: var(--secondary-text-color); }
  .set-line { display: flex; align-items: center; gap: var(--fp-s3); padding: var(--fp-s2) 0;
              font-size: var(--f-13); border-top: 1px solid var(--divider-color); }
  .set-line:first-of-type { border-top: 0; }
  .set-line ha-icon { --mdc-icon-size: 18px; width: 18px; height: 18px; }
  .set-line .right { margin-left: auto; color: var(--secondary-text-color); font-size: var(--f-12-5);
                     font-variant-numeric: tabular-nums; }
  h3.sec { font-size: var(--f-14); margin: 0 0 var(--fp-s1); }
  p.secsub { font-size: var(--f-12); color: var(--secondary-text-color); margin: 0 0 var(--fp-s3); }

  /* ---------- editors (phase 2) ---------- */
  .toolbar { display: flex; align-items: center; gap: var(--fp-s3); flex-wrap: wrap; margin: 0 0 var(--fp-s3); }
  /* Second and later blocks of the Réglages tab need air above them. */
  .toolbar.section-head { margin-top: var(--fp-s5); }
  .toolbar p.secsub { margin-bottom: 0; }
  .toolbar .spacer, .actions .spacer, .c-head .spacer, .sk-top .spacer, .ed-head .spacer { flex: 1; }
  .card.clickable { cursor: pointer; }
  .card.clickable:hover { border-color: var(--primary-color); }
  .card.drop { border-color: var(--primary-color); border-style: dashed; }
  .card.dragging { opacity: .45; }
  /* A tile whose last row is the head or the chips must not keep their bottom gap. */
  .card > .c-head:last-child, .card > .chips:last-child { margin-bottom: 0; }
  .c-head .chev { color: var(--secondary-text-color); --mdc-icon-size: 20px; width: 20px; height: 20px; }

  .field { display: flex; align-items: center; gap: var(--fp-s3); padding: var(--fp-s2) 0;
           border-top: 1px solid var(--divider-color); font-size: var(--f-13); }
  .field:first-of-type { border-top: 0; }
  .field.vertical { display: block; }
  .field .flabel { flex: 1; font-weight: 500; }
  .field .fhint { display: block; font-size: var(--f-11); color: var(--secondary-text-color); font-weight: 400; }
  .ftext, .fselect { flex: 1 1 200px; min-width: 0; height: var(--fp-ctl-h); font: inherit;
                     font-size: var(--f-13); padding: 0 var(--fp-s3); border-radius: var(--fp-field-r);
                     border: 1px solid var(--divider-color); background: var(--card-background-color);
                     color: var(--primary-text-color); }
  .ftext.fnum { flex: 0 0 110px; text-align: right; }
  .funit { color: var(--secondary-text-color); font-size: var(--f-12-5); flex: none; }
  .field.switch input { accent-color: var(--primary-color); width: 18px; height: 18px; flex: none; }
  .field.num { display: block; }
  .field.num .fhead { display: flex; align-items: center; gap: var(--fp-s2); }
  .field.num .fval { margin-left: auto; font-weight: 700; font-variant-numeric: tabular-nums; }
  .field.num input[type=range] { width: 100%; accent-color: var(--primary-color); }
  .field.ovr { background: color-mix(in srgb, var(--fp-warn) 10%, transparent);
               border-radius: var(--fp-field-r); padding-left: var(--fp-s2); padding-right: var(--fp-s2); }
  /* Icon-only, so it needs a real hit target of its own: the glyph is 16px but
     the button is 24px square, pulled back vertically to keep the row height. */
  .revert { display: inline-flex; align-items: center; justify-content: center; flex: none;
            width: 24px; height: 24px; margin: -2px 0; padding: 0; border: 0; border-radius: 50%;
            background: transparent; color: var(--fp-warn); cursor: pointer; }
  .revert:hover { background: color-mix(in srgb, var(--fp-warn) 18%, transparent); }
  .revert:focus-visible { outline: 2px solid var(--fp-warn); outline-offset: 1px; }
  /* An author display rule outranks the UA's [hidden] { display: none }, so the
     row's hidden flag needs restating here or the affordance leaks onto the
     inherited rows and the section counter stops matching what is marked. */
  .revert[hidden] { display: none; }
  .revert ha-icon { --mdc-icon-size: 16px; width: 16px; height: 16px; }
  .mini.ovr { color: var(--fp-warn); background: color-mix(in srgb, var(--fp-warn) 14%, transparent); }
  .chip.ovr { color: var(--fp-warn); border-color: color-mix(in srgb, var(--fp-warn) 45%, transparent); }
  .chip.auto { color: var(--primary-color); border-color: color-mix(in srgb, var(--primary-color) 45%, transparent); }
  .chip.lock { color: var(--fp-bad); border-color: color-mix(in srgb, var(--fp-bad) 45%, transparent); }
  .status { display: flex; align-items: center; gap: var(--fp-sh); flex-wrap: wrap;
            margin-bottom: var(--fp-s3); font-size: var(--f-12-5); }
  .status .smode { display: inline-flex; align-items: center; gap: var(--fp-sh); font-weight: 600;
                   border-radius: var(--fp-pill-r); padding: var(--fp-s0) var(--fp-s2); }
  .status .smode ha-icon { --mdc-icon-size: 14px; width: 14px; height: 14px; }
  .status .spos { color: var(--secondary-text-color); font-variant-numeric: tabular-nums; }
  .status .spos.big { color: var(--primary-text-color); font-weight: 600; }
  .gauge.big { width: 48px; height: 6px; border-radius: 3px; }
  /* The cover's schedules on one line: the time, then what the cover does,
     morning then evening, the next one in the accent colour. The whole line
     opens the Schedules tab. */
  .sched-row { display: flex; flex-wrap: wrap; align-items: center; gap: var(--fp-s1) var(--fp-s4); width: 100%;
               margin: 0 0 var(--fp-s3); padding: var(--fp-s0) 0; border: 0; border-radius: var(--fp-field-r);
               background: none; font: inherit; font-size: var(--f-12-5);
               color: var(--primary-text-color); text-align: left; cursor: pointer; }
  .sched-row:focus-visible { outline: var(--fp-focus); outline-offset: var(--fp-focus-off); }
  .sched-row:hover .lbl { text-decoration: underline; }
  .sched-row .ev { display: inline-flex; align-items: center; gap: var(--fp-sh); min-width: 0; }
  .sched-row .t { display: inline-flex; align-items: center; gap: var(--fp-s1); color: var(--secondary-text-color);
                  font-variant-numeric: tabular-nums; }
  .sched-row .t b { font-weight: 500; }
  .sched-row ha-icon { --mdc-icon-size: 14px; width: 14px; height: 14px; flex: none; }
  .sched-row .a { display: inline-flex; align-items: center; gap: var(--fp-s1); font-weight: 500; min-width: 0; }
  .sched-row .lbl { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .sched-row .dot { width: 8px; height: 8px; border-radius: 50%; flex: none; }
  .sched-row .none .a, .sched-row .done .a { color: var(--secondary-text-color); font-weight: 400; }
  .sched-row .next .t { color: var(--primary-color); }
  .sched-row .tag { font-size: var(--f-11); font-weight: 600; color: var(--primary-color); }
  .sched-row .k-mem { color: var(--secondary-text-color); }
  .sched-row .k-now { color: var(--primary-color); }
  .sched-hint { display: flex; align-items: flex-start; gap: var(--fp-sh); margin: calc(var(--fp-s2) * -1) 0 var(--fp-s3);
                font-size: var(--f-12); color: var(--secondary-text-color); }
  .sched-hint ha-icon { --mdc-icon-size: 14px; width: 14px; height: 14px; flex: none; margin-top: 1px; }
  .sched-hint.mem ha-icon { color: var(--primary-color); }
  .sched-hint.warn { color: var(--fp-warn); }
  .ed-sched .sched-hint { margin-bottom: 0; }
  .chip.safety { color: var(--fp-bad); border-color: color-mix(in srgb, var(--fp-bad) 45%, transparent); }
  .chip.inhib { color: var(--fp-warn); border-color: color-mix(in srgb, var(--fp-warn) 45%, transparent); }
  details.ents summary { cursor: pointer; color: var(--primary-color); font-size: var(--f-13);
                         margin-top: var(--fp-s3); }
  .ent-list { columns: 2 300px; column-gap: var(--fp-s5); font-size: var(--f-12);
              margin: var(--fp-s2) 0 0; padding: 0; list-style: none; }
  .ent-list li { padding: var(--fp-s0) 0; break-inside: avoid; display: flex; gap: var(--fp-s2);
                 justify-content: space-between; }
  .ent-list code { font-family: ui-monospace, monospace; }
  .ent-list span { color: var(--secondary-text-color); white-space: nowrap; overflow: hidden;
                   text-overflow: ellipsis; }
  .chip.timer { color: var(--primary-color); border-color: color-mix(in srgb, var(--primary-color) 45%, transparent); }
  .chip.prio { color: var(--fp-bad); border-color: color-mix(in srgb, var(--fp-bad) 45%, transparent);
               background: color-mix(in srgb, var(--fp-bad) 8%, transparent); }
  /* A selector row's hint sits between its label and the control. */
  .field.vertical .fhint { margin: calc(var(--fp-s1) * -1) 0 var(--fp-s2); }

  /* ---------- generated entities ---------- */
  .stats { display: flex; flex-wrap: wrap; gap: var(--fp-s5) calc(var(--fp-s5) * 2); }
  .stat-top { display: flex; align-items: center; gap: var(--fp-s2); }
  .stat-top ha-icon { --mdc-icon-size: 18px; width: 18px; height: 18px; color: var(--secondary-text-color); }
  .stat-n { font-size: var(--f-24); font-weight: 600; line-height: 1.1; }
  .stat-k { font-size: var(--f-12); color: var(--secondary-text-color); margin-top: var(--fp-s0); }
  .stat-total { font-size: var(--f-12); color: var(--secondary-text-color); margin: var(--fp-s4) 0 0; }

  details.sect { background: var(--card-background-color); border: 1px solid var(--divider-color);
                 border-radius: var(--ha-card-border-radius, 12px); padding: 0 var(--fp-s4);
                 margin-bottom: var(--fp-s2); }
  details.sect summary { display: flex; align-items: center; gap: var(--fp-s2); padding: var(--fp-s3) 0;
                         cursor: pointer; font-weight: 600; font-size: var(--f-13); list-style: none; }
  details.sect summary::-webkit-details-marker { display: none; }
  details.sect summary ha-icon { --mdc-icon-size: 18px; width: 18px; height: 18px;
                                 color: var(--secondary-text-color); }
  details.sect[open] summary { border-bottom: 1px solid var(--divider-color); }
  details.sect > .field:last-of-type { margin-bottom: var(--fp-s3); }

  .actions { display: flex; align-items: center; gap: var(--fp-s2); }
  .actions.card { margin-top: var(--fp-s3); }

  /* ---------- schedules ---------- */
  .blk { margin-bottom: var(--fp-s3); }
  .sched-body[hidden] { display: none; }
  .seg.sched-seg { margin: 0; flex: none; }
  .seg.sched-seg button { padding: 0 var(--fp-s4); white-space: nowrap; }
  .sched-fields { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--fp-s2); margin: var(--fp-s3) 0; }
  @media (max-width: 720px) { .sched-fields { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
  .sf { background: var(--secondary-background-color); border-radius: var(--fp-ctl-r); padding: var(--fp-s2) var(--fp-s3);
        border-left: 3px solid var(--c); display: grid; gap: var(--fp-s0); align-content: start; }
  .sf.off { opacity: .55; }
  .sf-top { display: flex; justify-content: space-between; align-items: center; gap: var(--fp-sh); }
  .sf label { font-size: var(--f-11); text-transform: uppercase; letter-spacing: .06em; color: var(--secondary-text-color); }
  .sf input[type=time], .sf input[type=date] { font: inherit; font-size: var(--f-16); font-weight: 600;
        font-variant-numeric: tabular-nums; border: 0; background: transparent; color: var(--primary-text-color);
        padding: 0; width: 100%; }
  .sf input[type=checkbox] { accent-color: var(--c); width: 16px; height: 16px; margin: 0; cursor: pointer; }
  .sf-info { font-size: var(--f-11-5); color: var(--secondary-text-color); }
  .legend.sched-legend { margin: 0 0 var(--fp-s2); }
  .lg-line { width: 16px; height: 3px; border-radius: 2px; display: inline-block; }
  .lg-line.sw { height: 10px; background: var(--ce-band); }
  .sched-chart { position: relative; touch-action: none; }
  .sched-chart svg { display: block; width: 100%; height: auto; overflow: visible; user-select: none; }
  .sched-chart text { font-size: 11px; fill: var(--secondary-text-color); font-variant-numeric: tabular-nums; }
  .sched-chart .grid { stroke: var(--divider-color); stroke-width: 1; }
  .sched-chart .band { fill: var(--ce-band); }
  .sched-chart .brk { stroke: var(--primary-text-color); stroke-width: 1.5; }
  .sched-chart .brk-t { fill: var(--primary-text-color); font-weight: 600; paint-order: stroke;
                        stroke: var(--card-background-color); stroke-width: 3px; }
  .sched-chart .on-chip { fill: #fff; font-weight: 600; }
  .sched-chart .fixed-t { fill: var(--ce-h); font-weight: 600; paint-order: stroke;
                          stroke: var(--card-background-color); stroke-width: 3px; }
  .sched-chart .cross { stroke: var(--divider-color); }
  .sched-chart .handle { cursor: grab; }
  .sched-tip { position: absolute; pointer-events: none; background: var(--card-background-color);
               border: 1px solid var(--divider-color); border-radius: var(--fp-ctl-r);
               padding: var(--fp-sh) var(--fp-s2); font-size: var(--f-12); white-space: nowrap;
               box-shadow: 0 4px 14px rgba(0,0,0,.18); font-variant-numeric: tabular-nums; }
  .sched-tip[hidden] { display: none; }
  .sched-edit { position: absolute; z-index: 2; display: grid; gap: var(--fp-sh); min-width: 200px;
                background: var(--card-background-color); border: 1px solid var(--divider-color);
                border-radius: var(--fp-ctl-r); padding: var(--fp-s2) var(--fp-s3);
                box-shadow: 0 6px 20px rgba(0,0,0,.2); }
  .sched-edit label { font-size: var(--f-11); text-transform: uppercase; letter-spacing: .06em;
                      color: var(--secondary-text-color); }
  .sched-edit input { font: inherit; font-size: var(--f-16); font-weight: 600; font-variant-numeric: tabular-nums;
                      color: var(--primary-text-color); background: var(--secondary-background-color);
                      border: 1px solid var(--divider-color); border-radius: var(--fp-field-r); padding: var(--fp-s1) var(--fp-s2); }
  .sched-edit input[aria-invalid="true"] { border-color: var(--fp-warn); }
  .sched-edit .err { font-size: var(--f-12); color: var(--fp-warn); }
  .sched-edit .err[hidden] { display: none; }
  .sched-edit .btns { display: flex; gap: var(--fp-sh); justify-content: flex-end; }
  .sched-tip .d { color: var(--secondary-text-color); }
  .sched-warn { background: color-mix(in srgb, var(--fp-warn) 14%, transparent); border-radius: var(--fp-ctl-r);
                padding: var(--fp-s2) var(--fp-s3); font-size: var(--f-12-5); margin-top: var(--fp-s2); }
  .sched-warn[hidden] { display: none; }
  .sched-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
                 gap: var(--fp-s2) var(--fp-s4); margin-top: var(--fp-s3); }
  .sched-stats div { display: grid; }
  .sched-stats .k { font-size: var(--f-11); text-transform: uppercase; letter-spacing: .05em; color: var(--secondary-text-color); }
  .sched-stats .v { font-size: var(--f-17); font-weight: 600; font-variant-numeric: tabular-nums; }
  .sched-stats .s { font-size: var(--f-11-5); color: var(--secondary-text-color); }
  .t-scroll { overflow-x: auto; }
  table.assign { border-collapse: collapse; width: 100%; font-size: var(--f-13); }
  table.assign th { text-align: left; font-size: var(--f-11); text-transform: uppercase; letter-spacing: .05em;
                    color: var(--secondary-text-color); font-weight: 600; padding: var(--fp-s2);
                    border-bottom: 1px solid var(--divider-color); white-space: nowrap; }
  table.assign td { padding: var(--fp-s1) var(--fp-s2); border-bottom: 1px solid var(--divider-color); vertical-align: middle; }
  table.assign tr:last-child td { border-bottom: 0; }
  table.assign .rowh { padding: var(--fp-s1) 0; min-width: 180px; }
  table.assign .fselect { width: 100%; min-width: 120px; }
  table.assign .fselect:disabled { opacity: .45; }
  .toggles { display: flex; flex-wrap: wrap; gap: var(--fp-sh); margin: var(--fp-s1) 0 var(--fp-s2); }
  .toggle { display: inline-flex; align-items: center; gap: var(--fp-sh); font: inherit; font-size: var(--f-12-5);
            border: 1px solid var(--divider-color); border-radius: var(--fp-pill-r); background: transparent;
            color: var(--secondary-text-color); padding: var(--fp-s0) var(--fp-s2); cursor: pointer; }
  .toggle[aria-pressed="true"] { color: var(--primary-text-color); font-weight: 600;
            border-color: color-mix(in srgb, var(--primary-color) 60%, transparent);
            background: color-mix(in srgb, var(--primary-color) 12%, transparent); }
  .toggle .mdot { width: 8px; height: 8px; border-radius: 50%; }
  .grouped { border-top: 1px solid var(--divider-color); padding-top: var(--fp-s2); margin-top: var(--fp-s1); }
  /* A rule written as a sentence to complete: words, then the controls. */
  .sentence { display: flex; flex-wrap: wrap; align-items: center; gap: var(--fp-sh) var(--fp-s2);
              margin: var(--fp-s2) 0; font-size: var(--f-13-5, var(--f-13)); }
  .sentence .chipline { display: inline-flex; flex-wrap: wrap; gap: var(--fp-sh); }
  .sentence .ed-select.inline { height: 34px; min-width: 160px; }
  .addsel { height: 28px; padding: 0 var(--fp-s2); border-radius: var(--fp-pill-r); cursor: pointer;
            border: 1px dashed var(--divider-color); background: transparent; color: var(--secondary-text-color);
            font: inherit; font-size: var(--f-12-5); }
  .addsel[hidden], .ed-sub[hidden] { display: none; }
  .toggle .x { --mdc-icon-size: 14px; width: 14px; height: 14px; color: var(--secondary-text-color); }
  .toggle[aria-pressed="true"] .mdot { display: inline-block; }
  .ed-sub.inline { margin: 0 0 var(--fp-s2); }
  .grouped h4 { margin: 0; font-size: var(--f-13); }

  /* ---------- editors, 4.0 layout ----------
     One anatomy for every editor: an identity strip (plate + the fields that
     name the item), then cards that each answer one question, in two columns
     on a wide screen and one on a phone. */
  .ed-ident { display: grid; grid-template-columns: auto minmax(220px, 1.4fr) minmax(160px, .8fr) minmax(160px, .8fr);
              gap: var(--fp-s3) var(--fp-s4); align-items: end; }
  .ed-ident.three { grid-template-columns: auto minmax(220px, 1fr) minmax(220px, 1fr); }
  .ed-ident .line2 { grid-column: 2 / -1; display: flex; align-items: center; gap: var(--fp-s3); flex-wrap: wrap; }
  .ed-ident .line2 .status { margin: 0 0 0 auto; }
  .ed-ident ha-selector { margin: 0; }
  .ed-plate { width: 64px; height: 64px; border-radius: 16px; flex: none; align-self: start; overflow: hidden;
              display: flex; align-items: center; justify-content: center;
              background: var(--secondary-background-color); color: var(--secondary-text-color);
              border: 1px solid var(--divider-color); }
  .ed-plate ha-icon { --mdc-icon-size: 34px; width: 34px; height: 34px; }
  .ed-plate img { width: 100%; height: 100%; object-fit: cover; }
  .ed-lbl { display: block; font-size: var(--f-12); font-weight: 500; color: var(--secondary-text-color);
            margin-bottom: var(--fp-sh); }
  .ed-input, .ed-select { width: 100%; height: 44px; font: inherit; font-size: var(--f-14); padding: 0 var(--fp-s3);
              border-radius: var(--fp-field-r); border: 1px solid var(--divider-color);
              background: var(--secondary-background-color); color: var(--primary-text-color); }
  .ed-input.big { font-size: var(--f-17); font-weight: 600; }
  .ed-input.small { height: 36px; font-size: var(--f-13); width: 260px; max-width: 100%; }
  .ed-select.inline { width: auto; min-width: 200px; height: 40px; }
  .ed-preview { grid-column: 2 / -1; display: flex; align-items: center; gap: var(--fp-s2);
                font-size: var(--f-12); color: var(--secondary-text-color); }
  .mpill { display: inline-flex; align-items: center; gap: var(--fp-sh); padding: 3px 10px; border-radius: var(--fp-pill-r);
           font-size: var(--f-12-5); font-weight: 600; }
  .mpill ha-icon { --mdc-icon-size: 14px; width: 14px; height: 14px; }
  .colorpick { display: flex; align-items: center; gap: var(--fp-s2); height: 44px; }
  .colorpick input[type=color] { width: 36px; height: 36px; padding: 0; border: 0; border-radius: 50%;
                                 background: none; cursor: pointer; flex: none; }
  .colorpick input[type=color]::-webkit-color-swatch-wrapper { padding: 0; }
  .colorpick input[type=color]::-webkit-color-swatch { border: 2px solid var(--divider-color); border-radius: 50%; }
  .colorpick input[type=color]::-moz-color-swatch { border: 2px solid var(--divider-color); border-radius: 50%; }
  .colorpick .ed-input { width: 120px; font-family: ui-monospace, monospace; text-transform: uppercase; }
  .colorpick .ed-input[aria-invalid="true"] { border-color: var(--fp-warn); }

  .ed-cols { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: var(--fp-s4); align-items: start;
             margin-top: var(--fp-s4); }
  .ed-stack { display: grid; gap: var(--fp-s4); align-content: start; }
  .ed-card > h3 { display: flex; align-items: center; gap: var(--fp-s2); margin: 0 0 var(--fp-s0);
                  font-size: var(--f-14-5, var(--f-14)); font-weight: 600; }
  .ed-card > h3 > ha-icon { --mdc-icon-size: 18px; width: 18px; height: 18px; color: var(--secondary-text-color); }
  .ed-card > h3 .end { margin-left: auto; }
  .ed-sub { margin: 0 0 var(--fp-s3); font-size: var(--f-12-5); color: var(--secondary-text-color); line-height: 1.4; }
  .ed-note { display: flex; gap: var(--fp-sh); margin: var(--fp-s2) 0 0; font-size: var(--f-12);
             color: var(--secondary-text-color); line-height: 1.4; }
  .ed-note ha-icon, .info { --mdc-icon-size: 15px; width: 15px; height: 15px; flex: none; color: var(--secondary-text-color); }
  .ed-q { display: flex; align-items: center; gap: var(--fp-sh); margin: var(--fp-s1) 0 var(--fp-s2);
          font-size: var(--f-13-5, var(--f-13)); font-weight: 500; }
  .ed-sep { border-top: 1px solid var(--divider-color); margin: var(--fp-s3) 0; }
  .ed-head { display: flex; align-items: center; gap: var(--fp-s2); flex-wrap: wrap; margin: var(--fp-s5) var(--fp-s0) var(--fp-s3); }
  .ed-head h2 { margin: 0; font-size: var(--f-16); font-weight: 600; }
  .ed-head .spacer { flex: 1; }
  .ed-head .note-txt { font-size: var(--f-12-5); color: var(--secondary-text-color); }
  .linkbtn { display: inline-flex; align-items: center; gap: var(--fp-s1); border: 0; background: none; padding: 0;
             font: inherit; font-size: var(--f-12-5); font-weight: 500; color: var(--primary-color); cursor: pointer; }
  .linkbtn ha-icon { --mdc-icon-size: 15px; width: 15px; height: 15px; }

  /* An option row: icon tile, label + one line, a switch at the end. */
  .opt { display: flex; align-items: center; gap: var(--fp-s3); padding: var(--fp-s3) 0;
         border-top: 1px solid var(--divider-color); }
  .opt:first-of-type { border-top: 0; padding-top: var(--fp-s1); }
  .opt .txt { flex: 1; min-width: 0; }
  .opt .t { font-size: var(--f-13-5, var(--f-13)); font-weight: 500; }
  .opt .h { font-size: var(--f-12); color: var(--secondary-text-color); margin-top: var(--fp-s0); line-height: 1.35; }
  .tile { width: 32px; height: 32px; border-radius: var(--fp-ctl-r); flex: none; display: flex; align-items: center;
          justify-content: center; background: var(--secondary-background-color); color: var(--secondary-text-color); }
  .tile ha-icon { --mdc-icon-size: 18px; width: 18px; height: 18px; }
  .tile.on { color: var(--primary-color); background: color-mix(in srgb, var(--primary-color) 14%, transparent); }
  .tsw { position: relative; width: 36px; height: 20px; flex: none; border: 0; padding: 0; border-radius: 10px;
         background: color-mix(in srgb, var(--secondary-text-color) 45%, transparent); cursor: pointer; }
  .tsw::after { content: ""; position: absolute; top: 2px; left: 2px; width: 16px; height: 16px; border-radius: 50%;
                background: var(--card-background-color); transition: left .15s; }
  .tsw[aria-checked="true"] { background: var(--primary-color); }
  .tsw[aria-checked="true"]::after { left: 18px; background: #fff; }
  .tsw:focus-visible { outline: var(--fp-focus); outline-offset: var(--fp-focus-off); }
  .opt-more { margin: calc(var(--fp-s1) * -1) 0 var(--fp-s2) 44px; padding: var(--fp-s2) var(--fp-s3);
              border-radius: var(--fp-ctl-r); background: var(--secondary-background-color);
              display: flex; align-items: center; gap: var(--fp-s2); flex-wrap: wrap; font-size: var(--f-13); }
  .opt-more input { width: 72px; height: 32px; text-align: right; font: inherit; font-size: var(--f-13);
                    border-radius: var(--fp-field-r); border: 1px solid var(--divider-color);
                    background: var(--card-background-color); color: var(--primary-text-color); padding: 0 var(--fp-s2); }
  .opt-more select { height: 32px; font: inherit; font-size: var(--f-13); border-radius: var(--fp-field-r);
                     border: 1px solid var(--divider-color); background: var(--card-background-color);
                     color: var(--primary-text-color); padding: 0 var(--fp-s2); }

  /* The mode's three behaviours, side by side. */
  .bseg { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--fp-s1); padding: var(--fp-s1);
          background: var(--secondary-background-color); border-radius: 10px; }
  .bseg button { display: flex; flex-direction: column; align-items: center; gap: var(--fp-s1); padding: 10px 6px;
                 border: 0; border-radius: 7px; background: transparent; font: inherit; font-size: var(--f-13);
                 font-weight: 500; color: var(--secondary-text-color); cursor: pointer; text-align: center; }
  .bseg button ha-icon { --mdc-icon-size: 22px; width: 22px; height: 22px; }
  .bseg button small { font-size: var(--f-11); font-weight: 400; }
  .bseg button[aria-pressed="true"] { background: var(--card-background-color); color: var(--primary-text-color);
                 font-weight: 600; box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--bc) 60%, transparent); }
  .bseg button[aria-pressed="true"] ha-icon { color: var(--bc); }
  .toggle ha-icon { --mdc-icon-size: 14px; width: 14px; height: 14px; color: var(--primary-color); }
  .toggle[aria-pressed="true"] .mdot { display: none; }
  .toggle:not([aria-pressed="true"]) ha-icon.check { display: none; }
  .toggle.wx ha-icon { color: inherit; }
  .toggle.wx[aria-pressed="true"] ha-icon { color: var(--primary-color); }
  details.adv > summary { display: flex; align-items: center; gap: var(--fp-s2); cursor: pointer; list-style: none; }
  details.adv > summary::-webkit-details-marker { display: none; }
  details.adv > summary h3 { margin: 0; flex: 1; font-size: var(--f-14); font-weight: 600; }
  details.adv > summary > ha-icon { --mdc-icon-size: 18px; width: 18px; height: 18px; color: var(--secondary-text-color); }
  details.adv[open] > summary .chev-d { transform: rotate(180deg); }
  details.adv > .adv-body { margin-top: var(--fp-s2); }
  .badge { font-size: var(--f-11-5); color: var(--secondary-text-color); border: 1px solid var(--divider-color);
           border-radius: 12px; padding: var(--fp-s0) var(--fp-s2); }

  /* Entities as chips, plus one picker to add another. */
  .prot { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: var(--fp-s5); }
  .prot h4 { display: flex; align-items: center; gap: var(--fp-s2); margin: 0; font-size: var(--f-13-5, var(--f-13)); }
  .prot h4 ha-icon { --mdc-icon-size: 18px; width: 18px; height: 18px; }
  .prot .safety h4 ha-icon { color: var(--fp-bad); }
  .prot .pause h4 ha-icon { color: var(--fp-warn); }
  .prot .pbody { margin-left: 26px; }
  .prot .pbody > p { margin: var(--fp-s0) 0 var(--fp-s2); font-size: var(--f-12); color: var(--secondary-text-color); }
  .prot .ex { margin: var(--fp-s2) 0 0; font-size: var(--f-11-5); color: var(--secondary-text-color); }
  .ents { display: flex; flex-wrap: wrap; gap: var(--fp-s2); margin-bottom: var(--fp-s2); }
  .ents:empty { display: none; }
  .ent { display: inline-flex; align-items: center; gap: var(--fp-s2); padding: var(--fp-sh) var(--fp-sh) var(--fp-sh) var(--fp-s3);
         border-radius: var(--fp-ctl-r); background: var(--secondary-background-color); border: 1px solid var(--divider-color);
         font-size: var(--f-13); min-width: 0; }
  .ent .eid { display: block; font-size: var(--f-11); color: var(--secondary-text-color); font-family: ui-monospace, monospace; }
  .ent .st { font-size: var(--f-11); font-weight: 600; padding: var(--fp-s0) var(--fp-sh); border-radius: 10px;
             background: color-mix(in srgb, var(--secondary-text-color) 18%, transparent); color: var(--secondary-text-color); }
  .ent .st.on { background: color-mix(in srgb, var(--fp-warn) 25%, transparent); color: var(--fp-warn); }
  .ent button { border: 0; background: none; padding: 0; color: var(--secondary-text-color); cursor: pointer;
                display: inline-flex; width: 24px; height: 24px; align-items: center; justify-content: center; border-radius: 50%; }
  .ent button:hover { background: color-mix(in srgb, var(--secondary-text-color) 18%, transparent); }
  .ent button ha-icon { --mdc-icon-size: 16px; width: 16px; height: 16px; }
  .chipline { display: flex; flex-wrap: wrap; gap: var(--fp-sh); }
  .chipline .chip ha-icon { --mdc-icon-size: 13px; width: 13px; height: 13px; }

  /* A number: box + unit on the right, one hint line, a short slider below. */
  .numf { display: grid; grid-template-columns: 1fr auto; gap: var(--fp-s0) var(--fp-s3); align-items: center;
          padding: 10px 0; border-top: 1px solid var(--divider-color); }
  .numf.first, .numf:first-child { border-top: 0; }
  .numf .t { display: flex; align-items: center; gap: var(--fp-sh); flex-wrap: wrap; font-size: var(--f-13-5, var(--f-13)); font-weight: 500; }
  .numf .h { grid-column: 1; font-size: var(--f-12); color: var(--secondary-text-color); line-height: 1.35; }
  .numf .val { grid-row: 1 / span 2; grid-column: 2; display: flex; align-items: center; gap: var(--fp-sh); }
  .numf input[type=number] { width: 68px; height: 32px; text-align: right; font: inherit; font-size: var(--f-13-5, var(--f-13));
          font-weight: 600; font-variant-numeric: tabular-nums; border-radius: var(--fp-field-r);
          border: 1px solid var(--divider-color); background: var(--secondary-background-color);
          color: var(--primary-text-color); padding: 0 var(--fp-sh); }
  .numf .u { font-size: var(--f-12-5); color: var(--secondary-text-color); min-width: 24px; }
  .numf .from { font-size: var(--f-11-5); font-weight: 400; color: var(--secondary-text-color); }
  /* The slider: a light track, the colour on the fill alone (--p, see
     paintRange), the thumb a ring of that colour. Amber on an override. */
  .numf .rwrap input[type=range], .pos-slider input[type=range] { width: 100%; height: 4px; margin: 8px 0 4px; border-radius: 2px;
         -webkit-appearance: none; appearance: none; cursor: pointer;
         background: linear-gradient(to right, var(--rc, var(--primary-color)) var(--p, 0%),
                     color-mix(in srgb, var(--secondary-text-color) 28%, transparent) var(--p, 0%)); }
  .numf .rwrap input[type=range]::-webkit-slider-thumb, .pos-slider input[type=range]::-webkit-slider-thumb { -webkit-appearance: none; appearance: none; width: 16px; height: 16px;
         border-radius: 50%; background: var(--card-background-color); border: 2px solid var(--rc, var(--primary-color)); }
  .numf .rwrap input[type=range]::-moz-range-thumb, .pos-slider input[type=range]::-moz-range-thumb { width: 12px; height: 12px; border-radius: 50%;
         background: var(--card-background-color); border: 2px solid var(--rc, var(--primary-color)); }
  .numf .rwrap input[type=range]::-moz-range-track, .pos-slider input[type=range]::-moz-range-track { background: transparent; }
  .numf.ovr { --rc: var(--fp-warn); }
  .numf .oline { grid-column: 1 / -1; display: flex; align-items: center; flex-wrap: wrap; gap: var(--fp-s1) var(--fp-s2);
                 margin-top: var(--fp-s1); font-size: var(--f-11-5); color: var(--secondary-text-color); }
  .numf .oline .olab { color: var(--fp-warn); font-weight: 600; }
  .numf:not(.ovr) .oline { display: none; }
  .numf.ovr { background: color-mix(in srgb, var(--fp-warn) 9%, transparent); border-radius: var(--fp-field-r);
              margin: 0 calc(var(--fp-s2) * -1); padding-left: var(--fp-s2); padding-right: var(--fp-s2); }
  .numf.ovr input[type=number] { border-color: color-mix(in srgb, var(--fp-warn) 60%, transparent); color: var(--fp-warn); }
  .numf:not(.ovr) .from { display: none; }
  /* Two thumbs on one track: the ranges overlap, only their thumbs catch the pointer. */
  .dual { grid-column: 1 / -1; position: relative; height: 20px; margin-top: var(--fp-sh); }
  .dual .track { position: absolute; left: 0; right: 0; top: 8px; height: 4px; border-radius: 2px;
                 background: color-mix(in srgb, var(--secondary-text-color) 35%, transparent); }
  .dual .track i { position: absolute; top: 0; bottom: 0; border-radius: 2px; background: var(--primary-color); }
  .numf.ovr .dual .track i { background: var(--fp-warn); }
  .dual .track .axis { position: absolute; top: -4px; width: 2px; height: 12px; margin-left: -1px;
                       background: var(--secondary-text-color); }
  .numf .ends { grid-column: 1 / -1; display: flex; justify-content: space-between;
                font-size: 11px; color: var(--secondary-text-color); margin-top: 2px; }
  .dual input[type=range] { position: absolute; inset: 0; width: 100%; margin: 0; pointer-events: none;
                            -webkit-appearance: none; appearance: none; background: transparent; }
  .dual input[type=range]::-webkit-slider-runnable-track { background: transparent; }
  .dual input[type=range]::-moz-range-track { background: transparent; }
  .dual input[type=range]::-webkit-slider-thumb { pointer-events: auto; -webkit-appearance: none; appearance: none;
         width: 16px; height: 16px; border-radius: 50%; border: 0; background: var(--primary-color); cursor: pointer; }
  .dual input[type=range]::-moz-range-thumb { pointer-events: auto; width: 16px; height: 16px; border-radius: 50%;
         border: 0; background: var(--primary-color); cursor: pointer; }
  .numf.ovr .dual input[type=range]::-webkit-slider-thumb { background: var(--fp-warn); }
  .numf.ovr .dual input[type=range]::-moz-range-thumb { background: var(--fp-warn); }
  .numf.sep-top { border-top: 1px solid var(--divider-color); margin-top: var(--fp-s1); }
  .sect.dim .sect-body { opacity: .5; }
  .withfig { display: grid; grid-template-columns: 200px minmax(0, 1fr); gap: var(--fp-s4); align-items: start; }
  /* Every sketch of the cover editor: a caption, then the drawing at the
     width of its box and the height its proportions give, so it fills the box
     on every screen. The top view and the profile are drawn 225 and 150 wide
     for the 1.5 / 1 columns they sit in: the two come out the same height.
     Labels get a halo of the background, to stay legible over a line. */
  .fig { background: var(--secondary-background-color); border-radius: 10px; padding: var(--fp-sh) var(--fp-sh) var(--fp-s1); }
  .fig .cap, .fig2 .cap { display: block; font-size: var(--f-10-5); letter-spacing: .05em; text-transform: uppercase;
                          padding: 0 var(--fp-s1); color: var(--secondary-text-color); }
  .fig svg, .fig2 svg { display: block; width: 100%; height: auto; margin: 0 auto; }
  .fig svg { aspect-ratio: 170 / 152; }
  .fig2 .figv:first-child svg { aspect-ratio: 225 / 150; }
  .fig2 .figv:nth-child(2) svg { aspect-ratio: 1; }
  .fig text { font-size: 8px; font-family: inherit; }
  .fig text, .fig2 text { paint-order: stroke; stroke: var(--secondary-background-color); stroke-width: 2.5px;
                          stroke-linejoin: round; }


  /* The detection card: a top view and a profile side by side, a legend, then
     one group per rule, each marked like its shape on the picture. */
  .fig2 { display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr); gap: var(--fp-s2);
          color: var(--secondary-text-color); }
  .fig2 .figv { background: var(--secondary-background-color); border-radius: 10px; padding: var(--fp-sh) var(--fp-sh) var(--fp-s1); }
  .fig2 svg text { font-size: 7px; font-family: inherit; }
  .flegend { grid-column: 1 / -1; display: flex; flex-wrap: wrap; gap: var(--fp-s1) var(--fp-s4); font-size: var(--f-12); }
  .flegend span { display: inline-flex; align-items: center; gap: var(--fp-sh); }
  .flegend span[hidden] { display: none; }
  .lg-sun::before, .g-sun h4::before { content: ""; width: 18px; height: 10px; border-radius: 3px; flex: none;
          background: color-mix(in srgb, var(--ce-b-shade) 30%, transparent); border: 1px dashed var(--ce-b-shade); }
  .lg-shade::before, .g-shade h4::before { content: ""; width: 18px; height: 10px; border-radius: 3px; flex: none;
          border: 2px dashed var(--primary-color); }
  .lg-dot::before { content: ""; width: 10px; height: 10px; border-radius: 50%; background: var(--ce-b-shade); }
  .sgroup { margin-top: var(--fp-s3); border-top: 1px solid var(--divider-color); padding-top: var(--fp-s2); }
  .sgroup h4 { display: flex; align-items: center; gap: var(--fp-s2); margin: 0 0 var(--fp-s1);
               font-size: var(--f-13); font-weight: 600; }
  /* A word placed under one value of a double slider (the zenith). */
  .numf .ends { position: relative; }
  .numf .ends .at { position: absolute; transform: translateX(-50%); }
  /* Facade slope: a cross-section beside its controls. */
  .slope { display: grid; grid-template-columns: 240px minmax(0, 520px); gap: 28px; align-items: center; }
  .slope-sketch { display: block; width: 100%; height: auto; aspect-ratio: 220 / 120;
                  background: var(--secondary-background-color); border-radius: 10px; }
  .slope .azrow input[type=range] { flex: 1; min-width: 120px; accent-color: var(--primary-color); }
  .slope .azrow[hidden] { display: none; }
  /* Facade compass. */
  .orient { display: grid; grid-template-columns: 240px 1fr; gap: 28px; align-items: center; }
  .compass { width: 240px; height: 240px; touch-action: none; cursor: grab; user-select: none; }
  .compass text { font-size: 13px; font-weight: 600; }
  .dial { display: grid; justify-items: center; gap: var(--fp-s1); }
  .compass-sides { display: flex; justify-content: space-between; width: 240px; max-width: 100%;
                   font-size: var(--f-12-5); color: var(--secondary-text-color); }
  .compass-sides b { color: var(--primary-text-color); }
  .azrow { display: flex; align-items: center; gap: var(--fp-s2); flex-wrap: wrap; font-size: var(--f-13);
           color: var(--secondary-text-color); }
  .azrow input { width: 84px; height: 40px; text-align: right; font: inherit; font-size: var(--f-17); font-weight: 600;
                 border-radius: var(--fp-field-r); border: 1px solid var(--divider-color);
                 background: var(--secondary-background-color); color: var(--primary-text-color); padding: 0 var(--fp-s2); }
  .dirs { display: flex; flex-wrap: wrap; gap: var(--fp-sh); margin: var(--fp-s3) 0 var(--fp-s1); }
  .dirs button { min-width: 44px; height: 32px; border-radius: var(--fp-ctl-r); border: 1px solid var(--divider-color);
                 background: transparent; color: var(--secondary-text-color); font: inherit; font-size: var(--f-13);
                 font-weight: 500; cursor: pointer; }
  .dirs button[aria-pressed="true"] { color: var(--primary-text-color); font-weight: 600;
                 border-color: color-mix(in srgb, var(--primary-color) 60%, transparent);
                 background: color-mix(in srgb, var(--primary-color) 14%, transparent); }

  /* Maison: two lists side by side. Réglages and the mode editor: one
     column, read top to bottom. */
  .house-cols { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 380px), 1fr));
                gap: var(--fp-s4); align-items: start; }
  .form-col { max-width: 880px; margin: 0 auto; }
  .ed-card > h3 .btn { margin-left: auto; height: 32px; padding: 0 var(--fp-s3); font-size: var(--f-12-5); }
  .ed-card > h3 .btn ha-icon { --mdc-icon-size: 16px; width: 16px; height: 16px; color: inherit; }
  .lrow { display: flex; align-items: center; gap: var(--fp-s3); padding: 10px var(--fp-s1); width: 100%;
          border: 0; border-top: 1px solid var(--divider-color); background: none; font: inherit; text-align: left;
          color: var(--primary-text-color); cursor: pointer; border-radius: var(--fp-field-r); }
  .lrow:first-child { border-top: 0; }
  .lrow:hover { background: color-mix(in srgb, var(--primary-color) 6%, transparent); }
  .lrow .nm { font-size: var(--f-14); font-weight: 500; }
  .lrow .meta { font-size: var(--f-12); color: var(--secondary-text-color); }
  .lrow .chev { margin-left: auto; color: var(--secondary-text-color); --mdc-icon-size: 20px; width: 20px; height: 20px; }
  .round { width: 36px; height: 36px; border-radius: 50%; flex: none; display: flex; align-items: center; justify-content: center;
           background: var(--secondary-background-color); border: 1px solid var(--divider-color); color: var(--secondary-text-color); }
  .round ha-icon { --mdc-icon-size: 20px; width: 20px; height: 20px; }
  .round.az { color: var(--primary-color); }
  .narrow { display: inline-flex; width: 14px; height: 14px; align-items: center; justify-content: center;
            color: inherit; flex: none; vertical-align: -2px; margin: 0 2px; }
  .narrow ha-icon { --mdc-icon-size: 13px; width: 13px; height: 13px; }
  .verdict { justify-self: start; margin: 0 0 var(--fp-s1); }
  .sg-line ha-selector { flex: 1 1 220px; min-width: 200px; margin: 0; }
  .sg-line .thr { flex: 0 1 auto; }
  .sg-line .thr-body { flex: 0 1 auto; }
  .wx-list { margin: 0 0 var(--fp-s1); }
  .toggle[hidden] { display: none; }
  .toggle.more { border-style: dashed; }
  .thr { display: flex; align-items: center; gap: var(--fp-s3); flex-wrap: wrap; }
  .seg.thr-seg { margin: 0; flex: none; }
  .seg.kind-seg { margin: 0; flex: none; }
  .seg.kind-seg button { flex: none; padding: 0 var(--fp-s4); }
  .seg.thr-seg button { flex: none; padding: 0 var(--fp-s3); }
  .thr-body { flex: 1 1 220px; display: flex; align-items: center; gap: var(--fp-sh); min-width: 0; }
  .thr-body ha-selector { flex: 1; margin: 0; }
  .thr-body input[type=number] { width: 84px; height: 40px; text-align: right; font: inherit; font-size: var(--f-14);
         font-weight: 600; border-radius: var(--fp-field-r); border: 1px solid var(--divider-color);
         background: var(--secondary-background-color); color: var(--primary-text-color); padding: 0 var(--fp-s2); }
  .thr-body .u { font-size: var(--f-12-5); color: var(--secondary-text-color); }
  .chip.ok { color: var(--fp-ok); border-color: color-mix(in srgb, var(--fp-ok) 45%, transparent); }
  .stats.compact { gap: var(--fp-s3) var(--fp-s5); margin-top: var(--fp-s2); }
  .stats.compact .stat-n { font-size: var(--f-20); }
  .actions.savebar { position: sticky; bottom: var(--fp-s2); z-index: 3; margin-top: var(--fp-s4);
                     padding: 10px var(--fp-s4); }
  .actions.savebar.dirty { border-color: color-mix(in srgb, var(--primary-color) 50%, transparent);
                           box-shadow: 0 -6px 24px rgba(0,0,0,.35); }
  /* Nothing to save: no Cancel, no Save, and the bar stays at the end of the
     page with Delete alone, or goes when there is no Delete either. */
  .actions.savebar:not(.dirty) { position: static; }
  .actions.savebar:not(.dirty) > .btn.primary, .actions.savebar:not(.dirty) > .btn.ghost { display: none; }
  .actions.savebar.bare:not(.dirty) { display: none; }
  .actions .pending { display: inline-flex; align-items: center; gap: var(--fp-sh); font-size: var(--f-12-5);
                      color: var(--primary-text-color); margin-right: var(--fp-s2); }
  .actions .pending[hidden] { display: none; }
  .actions .why { font-size: var(--f-12); color: var(--secondary-text-color); }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--primary-color); flex: none; }


  /* Inherited from the template vs the cover's own: a dashed grey box with a
     link, or amber with a bar, the template's value and a way back. */
  .numf { position: relative; }
  /* Inherited: a value at rest, its box only drawn under the pointer or the focus. */
  .numf.inh input[type=number] { background: transparent; border-color: transparent; }
  .numf.inh input[type=number]:hover, .numf.inh input[type=number]:focus { border-color: var(--divider-color); }
  .numf.ovr { padding-left: var(--fp-s3); }
  .numf.ovr::before { content: ""; position: absolute; left: 0; top: 6px; bottom: 6px; width: 3px;
                      border-radius: 2px; background: var(--fp-warn); }
  .rwrap { grid-column: 1 / -1; position: relative; }
  .rwrap .ghost { position: absolute; top: 4px; width: 2px; height: 12px; margin-left: -1px; display: none;
                  background: var(--secondary-text-color); pointer-events: none; }
  .numf.ovr .rwrap .ghost { display: block; }
  .revert.backtpl { width: auto; height: auto; margin: 0; padding: 1px 7px; gap: 3px; border-radius: 10px;
         font: inherit; font-size: var(--f-11-5); font-weight: 500;
         border: 1px solid color-mix(in srgb, var(--fp-warn) 45%, transparent); }
  .revert.backtpl ha-icon { --mdc-icon-size: 13px; width: 13px; height: 13px; }
  .sect h3 .cnt { margin-left: auto; font-size: var(--f-11-5); font-weight: 600; color: var(--fp-warn); }
  /* The cover editor's bar: back, then a stop per section, amber dot where
     the cover overrides its template. Stays on top while the page scrolls. */
  .ed-nav { position: sticky; top: 0; z-index: 4; display: flex; align-items: center; gap: var(--fp-s2);
            margin: 0 calc(var(--fp-s4) * -1) var(--fp-s3); padding: var(--fp-s2) var(--fp-s4);
            background: var(--primary-background-color); border-bottom: 1px solid var(--divider-color); }
  .ed-nav .btn { height: 34px; flex: none; }
  .ed-nav .stops { display: flex; gap: var(--fp-s0); padding: var(--fp-s1); overflow-x: auto; scrollbar-width: none;
                   background: var(--secondary-background-color); border-radius: var(--fp-ctl-r); min-width: 0; }
  .ed-nav .stops button { flex: none; height: 28px; padding: 0 var(--fp-s3); border: 0; border-radius: var(--fp-field-r);
                          background: transparent; font: inherit; font-size: var(--f-12-5); font-weight: 500;
                          color: var(--secondary-text-color); cursor: pointer; white-space: nowrap; }
  .ed-nav .stops button:hover { background: var(--card-background-color); color: var(--primary-text-color); }
  .ed-nav .stops button.has-own::after { content: ""; display: inline-block; width: 6px; height: 6px; margin-left: var(--fp-sh);
                                         border-radius: 50%; vertical-align: middle; background: var(--fp-warn); }
  .ed-anchor { scroll-margin-top: 64px; }
  .calc-from { margin: var(--fp-s1) 0 0; font-size: var(--f-13); color: var(--secondary-text-color);
               display: flex; align-items: center; flex-wrap: wrap; gap: var(--fp-s1); }
  .calc-from .linkbtn { font-size: var(--f-13); }
  .ed-cells { grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); }
  .ed-sched { margin-top: var(--fp-s3); padding-top: var(--fp-s2); border-top: 1px solid var(--divider-color); }
  .ed-sched .ed-lbl { margin-bottom: var(--fp-s1); }
  .seg.own-filter { margin: 0; flex: none; }
  .seg.own-filter button { flex: none; padding: 0 var(--fp-s3); }
  .ed-cols.own-only .numf.inh, .ed-cols.own-only .sect.no-own, .ed-cols.own-only .fig { display: none; }
  .ed-cols.own-only .withfig { grid-template-columns: minmax(0, 1fr); }
  .ed-note[hidden] { display: none; }
  .ed-note.warn, .ed-note.warn ha-icon { color: var(--fp-warn); }


  /* ---------- schedules, 4.0 layout ---------- */
  .sched-lead { margin: 0 var(--fp-s0) var(--fp-s3); font-size: var(--f-13); }
  .sched-head { display: flex; align-items: center; gap: var(--fp-s3) var(--fp-s4); flex-wrap: wrap; }
  /* The two schedules at a glance; the chosen one is outlined. */
  .sched-sum { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr));
               gap: var(--fp-s3); margin-bottom: var(--fp-s3); }
  .sched-k { display: grid; gap: var(--fp-s1); cursor: pointer; }
  .sched-k:hover { border-color: var(--primary-color); }
  .sched-k.on { border-color: var(--primary-color); box-shadow: inset 0 0 0 1px var(--primary-color); }
  .sched-k:focus-visible { outline: var(--fp-focus); outline-offset: var(--fp-focus-off); }
  .sk-top { display: flex; align-items: center; gap: var(--fp-s2); }
  .sk-top ha-icon { --mdc-icon-size: 20px; width: 20px; height: 20px; color: var(--secondary-text-color); }
  .sk-title { font-weight: 600; font-size: var(--f-14); }
  .sk-when { display: flex; align-items: baseline; flex-wrap: wrap; gap: var(--fp-s1) var(--fp-s2); }
  .sk-time { font-size: var(--f-24); font-weight: 700; font-variant-numeric: tabular-nums; }
  .sk-ref { font-size: var(--f-12-5); color: var(--secondary-text-color); }
  .sched-k.off .sk-time { font-size: var(--f-16); color: var(--secondary-text-color); font-weight: 500; }
  .sk-eff { display: flex; flex-wrap: wrap; gap: var(--fp-s1) var(--fp-s3); font-size: var(--f-12-5); }
  .sk-eff span { display: inline-flex; align-items: center; gap: var(--fp-sh); }
  .sched-k.off .sk-eff { color: var(--secondary-text-color); }
  .mdot { width: 8px; height: 8px; border-radius: 50%; flex: none; }
  .sched-hint[hidden] { display: none; }
  .sched-ref { display: inline-flex; align-items: center; gap: var(--fp-sh); font-size: var(--f-12-5); color: var(--secondary-text-color); }
  .sched-ref ha-icon { --mdc-icon-size: 16px; width: 16px; height: 16px; }
  .sched-groups { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr) minmax(0, .8fr);
                  gap: var(--fp-s3); margin: var(--fp-s4) 0 var(--fp-s1); align-items: start; }
  .sgrp { border: 1px solid var(--divider-color); border-radius: 10px; padding: 10px var(--fp-s3); }
  .sgrp h4 { display: flex; align-items: center; gap: var(--fp-sh); margin: 0 0 var(--fp-s2);
             font-size: var(--f-12); font-weight: 600; color: var(--secondary-text-color); }
  .sgrp h4 ha-icon { --mdc-icon-size: 15px; width: 15px; height: 15px; }
  .sgrp h4 .info { margin-left: auto; }
  .spair { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--fp-s2); }
  .spair.one { grid-template-columns: minmax(0, 1fr); margin-top: var(--fp-s2); }
  details.sfine > summary { display: flex; align-items: center; gap: var(--fp-sh); cursor: pointer; list-style: none;
                            font-size: var(--f-12-5); color: var(--secondary-text-color); padding: var(--fp-s1) 0; }
  details.sfine > summary::-webkit-details-marker { display: none; }
  details.sfine > summary ha-icon { --mdc-icon-size: 18px; width: 18px; height: 18px; color: var(--primary-color); }
  details.sfine[open] > summary .chev-d { transform: rotate(180deg); }
  /* The on/off of a bound or a crossing reads as a switch, in the field's own colour. */
  .sf input[type=checkbox] { -webkit-appearance: none; appearance: none; position: relative; flex: none;
         width: 28px; height: 16px; border-radius: 8px; margin: 0; cursor: pointer;
         background: color-mix(in srgb, var(--secondary-text-color) 45%, transparent); }
  .sf input[type=checkbox]::before { content: ""; position: absolute; top: 2px; left: 2px; width: 12px; height: 12px;
         border-radius: 50%; background: var(--card-background-color); transition: left .15s; }
  .sf input[type=checkbox]:checked { background: var(--c); }
  .sf input[type=checkbox]:checked::before { left: 14px; background: #fff; }
  .sf input[type=checkbox]:disabled { opacity: .4; cursor: default; }
  .sf input[type=checkbox]:focus-visible { outline: var(--fp-focus); outline-offset: var(--fp-focus-off); }
  table.assign tr.fac td { background: var(--secondary-background-color); font-size: var(--f-11); font-weight: 700;
         letter-spacing: .08em; text-transform: uppercase; color: var(--secondary-text-color); padding: var(--fp-s1) var(--fp-s2); }
  table.assign tr.all td { background: color-mix(in srgb, var(--primary-color) 7%, transparent); }
  table.assign tr.all .nm { font-weight: 600; }
  table.assign .fselect.msel { width: auto; min-width: 180px; max-width: 260px; height: 34px; border-left-width: 4px; }
  table.assign .sact.diff .fselect.msel, table.assign .sact.diff .spos input {
         border-color: color-mix(in srgb, var(--fp-warn) 60%, transparent);
         background: color-mix(in srgb, var(--fp-warn) 9%, var(--card-background-color)); }
  /* A scheduled position: its value, then whether it respects the lock or forces it. */
  table.assign .sact { display: flex; flex-wrap: wrap; align-items: center; gap: var(--fp-s1) var(--fp-s2); }
  table.assign .spos { display: flex; align-items: center; gap: var(--fp-s1); }
  table.assign .spos[hidden], table.assign .sflag[hidden] { display: none; }
  table.assign .spos input { width: 64px; height: 34px; text-align: right; font: inherit; font-size: var(--f-13);
         font-variant-numeric: tabular-nums; padding: 0 var(--fp-s2); border-radius: var(--fp-field-r);
         border: 1px solid var(--divider-color); background: var(--secondary-background-color); color: var(--primary-text-color); }
  table.assign .spct { font-size: var(--f-13); color: var(--secondary-text-color); }
  .seg.spos-seg { margin: 0 0 0 var(--fp-s1); flex: none; }
  .seg.spos-seg button { flex: none; display: flex; align-items: center; gap: var(--fp-sh); padding: 0 var(--fp-s3); white-space: nowrap; }
  .seg.spos-seg button ha-icon { --mdc-icon-size: 16px; width: 16px; height: 16px; }
  .seg.spos-seg button:disabled { opacity: .5; cursor: default; }
  table.assign .sflag { --mdc-icon-size: 18px; width: 18px; height: 18px; color: var(--fp-warn); cursor: help; }
  table.assign .fselect.msel.none { color: var(--secondary-text-color); font-style: italic; }
  .sched-diff-legend { display: inline-flex; align-items: center; gap: var(--fp-sh); font-size: var(--f-12); color: var(--secondary-text-color); }
  .sw-diff { display: inline-block; width: 22px; height: 12px; border-radius: 3px;
             border: 1px solid color-mix(in srgb, var(--fp-warn) 60%, transparent);
             background: color-mix(in srgb, var(--fp-warn) 9%, transparent); }

  @media (max-width: 720px) {
    /* The tabs take their own full row and share it; on the narrowest phones
       they scroll rather than push the page, the current one kept in view. */
    .tabs { flex: 1 1 100%; margin-left: 0; max-width: 100%; overflow-x: auto; scrollbar-width: none; }
    .tab { flex: 1 0 auto; padding: 0 var(--fp-s2); }
    /* The plate keeps the name beside it; everything else takes a full row. */
    .ed-ident, .ed-ident.three { grid-template-columns: auto minmax(0, 1fr); }
    .ed-ident > :not(.ed-plate):not(.wide) { grid-column: 1 / -1; }
    .ed-ident > * { min-width: 0; }
    .ed-ident .line2 .status { margin-left: 0; }
    .ed-input.small { width: 100%; }
    .ed-cols, .prot { grid-template-columns: minmax(0, 1fr); }
    .withfig { grid-template-columns: minmax(0, 1fr); }
    .fig2 { grid-template-columns: minmax(0, 1fr); }
    /* One under the other, the square profile and the cross-section would
       fill a whole screen: they keep a sketch's size. */
    .fig svg { max-width: 300px; }
    .fig2 .figv:nth-child(2) svg { max-width: 260px; }
    .orient { grid-template-columns: 1fr; justify-items: center; }
    .slope { grid-template-columns: 1fr; }
    .opt-more { margin-left: 0; }
    .sched-groups { grid-template-columns: minmax(0, 1fr); }
    /* The cover table fits a phone: lists shrink, the picture goes. */
    table.assign .rowh { min-width: 0; }
    table.assign .rowh .pic, table.assign .rowh img { display: none; }
    table.assign .fselect.msel { min-width: 0; width: 100%; }
    table.assign .sact { flex-direction: column; align-items: stretch; }
    /* In a column, the list's 200px basis would become its height. */
    table.assign .sact .fselect { flex: none; }
    table.assign .spos { flex-wrap: wrap; }
    .seg.spos-seg { margin-left: 0; }
    table.assign td, table.assign th { padding-left: var(--fp-s1); padding-right: var(--fp-s1); }
    table.assign th { white-space: normal; }
    .actions .why, .actions .ptext { display: none; }
  }

  @media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
`;

/* ---------- schedules: what the panel computes itself ----------
 *
 * The curve comes from the server (cover_extender/schedule/preview): Python is
 * the one place that computes it. The panel only converts between the stored
 * shape and the handles, and keeps the handles within their bounds while they
 * are dragged; the server validates again on save.
 */
const WS_SCHED_PREVIEW = `${DOMAIN}/schedule/preview`;
const SCHED_KINDS = ["morning", "evening"];
const P_YEAR = 365.2425;
const smod = (a, n) => ((a % n) + n) % n;
const hmFmt = (m) => { m = Math.round(smod(m, 1440)); return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`; };
const hmParse = (v) => { const [h, m] = String(v).split(":").map(Number); return h * 60 + m; };
const signedMin = (n) => `${n >= 0 ? "+" : "−"}${Math.abs(Math.round(n))} min`;
const schedDayOfYear = (year, month, day) => {
  if (month === 2 && day === 29) day = 28;
  return Math.min(365, Math.round((Date.UTC(year, month - 1, day) - Date.UTC(year, 0, 0)) / 864e5));
};
const schedDayDate = (j, year) => new Date(Date.UTC(year, 0, j));
const schedDayToIso = (j, year) => schedDayDate(j, year).toISOString().slice(0, 10);
const schedIsoToDay = (iso, year) => { const [, m, d] = iso.split("-").map(Number); return schedDayOfYear(year, m, d); };
const schedDayLabel = (j, year, style) => new Intl.DateTimeFormat(LANG,
  { day: "numeric", month: style === "short" ? "short" : "long", timeZone: "UTC" }).format(schedDayDate(j, year));

/* The hours each chart shows: morning 04:30–10:45, evening 15:30–23:30. A
   floor or a ceiling is kept inside them, so its handle can always be seen
   and grabbed; outside, it would never touch the curve anyway. */
const SCHED_RANGE = { morning: [270, 645], evening: [930, 1410] };
// Where a floor / ceiling starts when it is ticked on.
const SCHED_CLAMP_START = { morning: { fl: 435, ce: 570 }, evening: { fl: 1020, ce: 1320 } };
const schedInRange = (kind, m) => Math.min(SCHED_RANGE[kind][1], Math.max(SCHED_RANGE[kind][0], m));

/** Stored shape → the handles (minutes of the day, days of the year). */
function schedFromCfg(cfg, kind) {
  const year = new Date().getFullYear();
  const day = (v, fallback) => (v ? schedIsoToDay(`${year}-${v}`, year) : fallback);
  const fixed = cfg.type === "fixed";
  return {
    hi: hmParse(fixed ? cfg.time : cfg.max), lo: hmParse(fixed ? cfg.time : cfg.min),
    x1: { on: !fixed && !!cfg.cross_spring, j: day(cfg.cross_spring, 79) },
    x2: { on: !fixed && !!cfg.cross_autumn, j: day(cfg.cross_autumn, 266) },
    fl: { on: !!cfg.not_before,
          m: schedInRange(kind, cfg.not_before ? hmParse(cfg.not_before) : SCHED_CLAMP_START[kind].fl) },
    ce: { on: !!cfg.not_after,
          m: schedInRange(kind, cfg.not_after ? hmParse(cfg.not_after) : SCHED_CLAMP_START[kind].ce) },
  };
}

/** The handles → the stored shape. */
function schedToCfg(s) {
  const year = new Date().getFullYear();
  const out = s.hi === s.lo
    ? { type: "fixed", time: hmFmt(s.hi) }
    : {
      type: "curve", max: hmFmt(s.hi), min: hmFmt(s.lo),
      cross_spring: s.x1.on ? schedDayToIso(s.x1.j, year).slice(5) : null,
      cross_autumn: s.x2.on ? schedDayToIso(s.x2.j, year).slice(5) : null,
    };
  out.not_before = s.fl.on ? hmFmt(s.fl.m) : null;
  out.not_after = s.ce.on ? hmFmt(s.ce.m) : null;
  return out;
}

/** Move one time handle within its bounds. Returns the message to show, or "".
 *  *pv* is the last preview (its dst_gap); before the first one, no gap. A
 *  floor or a ceiling also stays within the chart of *kind*. */
function schedSetVal(pv, s, key, v, kind) {
  const W = T.sched, SNAP = 5, G = pv?.dst_gap || 0;
  if (key === "fl" || key === "ce") v = schedInRange(kind, v);
  const FL = s.fl.on ? s.fl.m : -1e9, CE = s.ce.on ? s.ce.m : 1e9, want = v;
  let msg = "";
  if (key === "hi") {
    v = Math.max(v, s.lo, FL);
    const d = v - s.lo;
    if ((d <= SNAP || d < G / 2) && s.lo >= FL) v = s.lo;
    else if (d < G) v = s.lo + G;
    s.hi = v;
    if (want < s.lo && v === s.lo) msg = W.clampHiLo;
    else if (want < FL && v === FL) msg = W.clampHiFl(hmFmt(FL));
  } else if (key === "lo") {
    v = Math.min(v, s.hi, CE);
    const d = s.hi - v;
    if ((d <= SNAP || d < G / 2) && s.hi <= CE) v = s.hi;
    else if (d < G) v = s.hi - G;
    s.lo = v;
    if (want > s.hi && v === s.hi) msg = W.clampLoHi;
    else if (want > CE && v === CE) msg = W.clampLoCe(hmFmt(CE));
  } else if (key === "both") {
    v = Math.min(Math.max(v, FL), CE); s.hi = s.lo = v;
  } else if (key === "fl") {
    v = Math.min(v, s.hi, s.ce.on ? s.ce.m - SNAP : 1e9); s.fl.m = v;
    if (v !== want) msg = v === s.hi ? W.clampFlHi(hmFmt(s.hi)) : W.clampFlCe(hmFmt(s.ce.m));
  } else if (key === "ce") {
    v = Math.max(v, s.lo, s.fl.on ? s.fl.m + SNAP : -1e9); s.ce.m = v;
    if (v !== want) msg = v === s.lo ? W.clampCeLo(hmFmt(s.lo)) : W.clampCeFl(hmFmt(s.fl.m));
  }
  if (!msg && G && (key === "hi" || key === "lo") && s.hi !== s.lo && Math.abs(s.hi - s.lo) === G
      && Math.abs(want - (key === "hi" ? s.hi : s.lo)) > 0) msg = W.clampGap;
  return msg;
}

/** Spring crossing on the half holding the 20 March equinox, autumn on the
 *  other, at least two days from the extreme days. */
function schedSetCross(pv, s, key, j, year) {
  if (!pv?.max_day) { s[key].j = j; return ""; }
  const JT = pv.min_day, JP = pv.max_day, L1 = pv.rising_days;
  const half = (d) => smod(d - JT, P_YEAR) < L1;
  const wantUp = half(79) === (key === "x1");
  const a = wantUp ? JT : JP, b = wantUp ? JP : JT;
  const len = smod(b - a, P_YEAR), k = smod(j - a, P_YEAR);
  let v = j, msg = "";
  if (k < 2 || k > len - 2) {
    const toA = Math.min(k, P_YEAR - k), toB = Math.abs(k - len);
    v = toA <= toB ? a + 2 : b - 2;
    v = ((Math.round(v) - 1 + 365) % 365) + 1;
    msg = T.sched.clampCross(key === "x1" ? T.sched.x1 : T.sched.x2,
      schedDayLabel(smod(a, 365) || 365, year, "long"), schedDayLabel(smod(b, 365) || 365, year, "long"));
  }
  s[key].j = v;
  return msg;
}

class CoverExtenderPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._tab = "volets";
    this._cfg = null;
    this._state = "loading"; // loading | ready | error
    this._pop = null;        // open popover state
    this._edit = null;       // open item editor: {section, idx, draft, clean}
    this._globalDraft = null; // global settings are edited in place, not in _edit
    this._globalClean = null; // its pristine copy, for the unsaved-changes guard
    this._liveNodes = [];    // mounted ha-selectors, refreshed on every render
  }

  /* Panel contract: HA sets hass on every state change — render once, then
     only refresh the hass reference of live HA elements. */
  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    // The reader's language is read off hass, so it is only known here. A change
    // of language counts as a change of everything: nothing on the page is drawn
    // from anything but T. Drafts live in _edit / _globalDraft and survive it.
    const relang = setLanguage(hass);
    if (first) { this._load(); return; }
    if (relang) { this._render(); return; }
    // Every live HA control needs the fresh hass, not just the popover's — but
    // this setter runs on every state-change batch, dozens of times a second on
    // a busy install. Querying the shadow tree here would walk 126 matrix cells
    // that hold no ha-selector at all, that often. The list is captured once per
    // render instead (_trackLiveNodes).
    for (const n of this._liveNodes) n.hass = hass;
    // The cover cards show live state (mode, position, lock, what holds the
    // cover back). Redraw them only when one of those states changed, and
    // never under an open editor.
    if (this._tab === "volets" && !this._edit && this._state === "ready") {
      const sig = this._statusSignature();
      if (sig !== this._statusSig) { this._statusSig = sig; this._render(); }
    }
  }
  get hass() { return this._hass; }
  set narrow(_) {}
  set route(_) {}
  set panel(_) {}

  connectedCallback() {
    if (!this.shadowRoot.firstChild) this._renderShell();
  }

  /* ---------- data ---------- */

  async _load() {
    this._state = "loading";
    this._render();
    try {
      this._cfg = await this._hass.connection.sendMessagePromise({ type: WS_GET });
      this._state = "ready";
    } catch (err) {
      console.error(`${DOMAIN}: config load failed`, err);
      this._state = "error";
    }
    this._render();
  }

  async _saveCovers(items) {
    await this._hass.connection.sendMessagePromise({
      type: WS_SAVE, section: "cover", data: items,
    });
    // Re-read from the source of truth rather than trusting the local copy.
    this._cfg = await this._hass.connection.sendMessagePromise({ type: WS_GET });
    this._render();
    toast(this, T.saved);
  }

  /* ---------- shell ---------- */

  _renderShell() {
    const style = document.createElement("style");
    style.textContent = STYLE;
    this.shadowRoot.append(style, el("div", "wrap"));
    // Capture runs BEFORE the control's own handler has touched the draft, so
    // the save bar looks again once the event is over.
    const sync = () => setTimeout(() => this._syncSaveBar?.(), 0);
    for (const ev of ["input", "change", "click", "pointerup", "keyup", "value-changed"]) {
      this.shadowRoot.addEventListener(ev, sync, true);
    }
  }

  _render() {
    if (!this.shadowRoot.firstChild) this._renderShell();
    const wrap = this.shadowRoot.querySelector(".wrap");
    wrap.replaceChildren();
    this._syncSaveBar = null;
    // The popover is mounted on the shadow root, so clearing .wrap does not
    // remove it — close it explicitly (also detaches its scroll listeners).
    this._closePopover();

    // header
    const bar = el("header", "bar");
    const logo = el("span", "logo");
    logo.append(icon("mdi:window-shutter-cog"));
    const titleBox = el("div");
    titleBox.append(el("div", "title", T.title));
    if (this._cfg?.version) titleBox.append(el("div", "ver", `v${this._cfg.version}`));
    bar.append(logo, titleBox);
    const tabs = el("nav", "tabs");
    tabs.setAttribute("role", "tablist");
    // Everyday tabs in the order of the work (covers, their modes, the link
    // between the two, the schedules); then, past a rule, the two set once.
    for (const key of ["volets", "modes", "matrice", "horaires", "|", "maison", "reglages"]) {
      if (key === "|") {
        const sep = el("span", "tab-sep");
        sep.setAttribute("role", "presentation");
        tabs.append(sep);
        continue;
      }
      const b = el("button", "tab", T.tabs[key]);
      b.setAttribute("role", "tab");
      b.setAttribute("aria-selected", String(this._tab === key));
      if (this._tab === key) this._tabBtn = b;
      // Leaving by a tab discards the draft exactly like the "← back" button
      // does. Keeping it alive would restore it silently on the way back, so
      // the two exits from an editor would mean opposite things.
      b.addEventListener("click", () => {
        if (!this._leaveEditor()) return;
        this._tab = key;
        this._render();
      });
      tabs.append(b);
    }
    bar.append(tabs);
    wrap.append(bar);
    requestAnimationFrame(() => {
      const on = tabs.querySelector('[aria-selected="true"]');
      if (on && tabs.scrollWidth > tabs.clientWidth) tabs.scrollLeft = on.offsetLeft - tabs.offsetLeft - (tabs.clientWidth - on.offsetWidth) / 2;
    });

    if (this._state === "loading") {
      wrap.append(el("div", "center", T.loading));
      return;
    }
    if (this._state === "error") {
      const box = el("div", "center");
      box.append(el("p", "", T.loadError));
      const retry = el("button", "btn", T.retry);
      retry.addEventListener("click", () => this._load());
      box.append(retry);
      wrap.append(box);
      return;
    }

    // The editors are built from ha-selector. WAIT for the chunk rather than
    // render now and re-render when it lands: that second render rebuilds every
    // node, so it would wipe whatever field the user had started typing in
    // while the chunk was in flight.
    if (this._tab !== "matrice" && !customElements.get("ha-selector")) {
      wrap.append(el("div", "center", T.loading));
      loadHaForm().then(() => this._render());
      return;
    }

    if (this._tab === "matrice") this._renderMatrix(wrap);
    else if (this._tab === "volets") this._renderCovers(wrap);
    else if (this._tab === "modes") this._renderModes(wrap);
    else if (this._tab === "horaires") this._renderSchedules(wrap);
    else if (this._tab === "maison") this._renderHouse(wrap);
    else this._renderSettings(wrap);

    this._trackLiveNodes();
    this._syncSaveBar?.();
  }

  /* ---------- unsaved-changes guard ---------- */

  /** Snapshot taken when an editor opens; equality against it is the dirty bit. */
  _openEditor(edit) {
    this._advOpen = undefined;
    this._ownOnly = false;
    this._picOpen = false;
    this._edit = { ...edit, clean: JSON.stringify(edit.draft) };
  }

  _dirty() {
    // Both, not the first one found: the Réglages tab can hold a dirty global
    // block AND an open facade editor at the same time, and _leaveEditor drops
    // the two together.
    if (this._edit && JSON.stringify(this._edit.draft) !== this._edit.clean) return true;
    if (this._globalDraft && JSON.stringify(this._globalDraft) !== this._globalClean) return true;
    if (this._schedDraft && JSON.stringify(this._schedDraft) !== this._schedClean) return true;
    return false;
  }

  /**
   * Drop the open editor, asking first when it holds unsaved edits.
   * Returns false when the user chose to stay — callers must then do nothing.
   */
  _leaveEditor() {
    if (this._dirty() && !window.confirm(T.discardConfirm)) return false;
    this._edit = null;
    this._globalDraft = null;
    this._globalClean = null;
    this._schedDraft = null;
    this._schedClean = null;
    return true;
  }

  /** Cache the mounted ha-selectors so `set hass` never queries the tree. */
  _trackLiveNodes() {
    this._liveNodes = this.shadowRoot.querySelectorAll("ha-selector");
  }

  /* ---------- shared lookups ---------- */

  _coverName(item) {
    const st = this._hass.states[item.entity_id];
    return st?.attributes?.friendly_name || item.entity_id;
  }

  _coverPic(item) {
    if (item.entity_picture) {
      const img = document.createElement("img");
      img.src = item.entity_picture;
      img.alt = "";
      return img;
    }
    const pic = el("span", "pic");
    pic.append(icon("mdi:window-shutter"));
    return pic;
  }

  /** Covers grouped by facade, facades in their configured order. */
  _grouped() {
    const order = this._cfg.facades.map((f) => f.name);
    const groups = new Map(order.map((n) => [n, []]));
    const rest = [];
    for (const c of this._cfg.covers) {
      if (groups.has(c.facade)) groups.get(c.facade).push(c);
      else rest.push(c);
    }
    if (rest.length) groups.set(null, rest);
    return groups;
  }

  /* ---------- MATRICE ---------- */

  _renderMatrix(wrap) {
    // One line above the table: how to use it, what the cells look like and,
    // on a phone, the choice between the table and the covers one by one.
    const tools = el("div", "m-tools");
    const hint = el("p", "m-hint");
    hint.append(icon("mdi:gesture-tap"), el("span", "", T.matrixHint));
    const legend = el("div", "legend");
    const lg = (cls, label) => {
      const s = el("span");
      s.append(el("i", `lg ${cls}`), document.createTextNode(label));
      return s;
    };
    legend.append(lg("fixed", T.legendFixed));
    for (const key of ["auto_shade", "solar_gain", "none"]) {
      const b = el("span");
      b.append(behaviorBadge(key), document.createTextNode(T.legendBehavior[key]));
      legend.append(b);
    }
    const le = el("span");
    le.append(icon("mdi:link-variant"), document.createTextNode(T.legendEntity));
    legend.append(le);
    const box = el("div", `m-box${this._mxView === "table" ? " as-table" : ""}`);
    const vseg = el("div", "seg m-view");
    const vbtns = [];
    for (const [k, label] of [["list", T.viewList], ["table", T.viewTable]]) {
      const b = el("button", "", label);
      b.type = "button";
      vbtns.push([b, k]);
      b.addEventListener("click", () => {
        this._mxView = k;
        box.classList.toggle("as-table", k === "table");
        for (const [o, ok] of vbtns) { o.classList.toggle("on", ok === k); o.setAttribute("aria-pressed", String(ok === k)); }
      });
      vseg.append(b);
    }
    for (const [o, ok] of vbtns) {
      const on = ok === (this._mxView || "list");
      o.classList.toggle("on", on);
      o.setAttribute("aria-pressed", String(on));
    }
    tools.append(hint, legend, vseg);
    wrap.append(tools);

    const scroll = el("div", "m-scroll");
    const table = el("table", "matrix");
    const thead = el("thead");
    const hr = el("tr");
    const corner = el("th", "corner");
    hr.append(corner);
    this._cfg.modes.forEach((m, i) => {
      const th = el("th");
      // The header opens the mode: what it does is one click away.
      const mh = el("button", "mh");
      mh.type = "button";
      mh.title = T.openMode(m.name);
      mh.addEventListener("click", () => {
        this._tab = "modes";
        this._openEditor({ section: "mode", idx: i, draft: { ...m } });
        this._render();
      });
      const mico = el("span", "mico");
      mico.style.background = `${m.color || "#888888"}26`;
      mico.style.color = m.color || "var(--secondary-text-color)";
      mico.append(icon(m.icon || "mdi:help-circle"));
      // What sets this mode apart, in words: the same as on its row in Modes.
      const tags = [];
      if (m.behavior) tags.push((m.behavior === "auto_shade" ? T.shading : T.solarGain).toLowerCase());
      if (m.duration) tags.push(`${m.duration} min`);
      if (m.lock) tags.push(T.lock);
      if (m.priority) tags.push(T.priority);
      if (m.hidden) tags.push(T.hidden);
      mh.append(mico, el("span", "", m.name), el("span", "tags", tags.join(" · ")));
      th.append(mh);
      hr.append(th);
    });
    thead.append(hr);
    table.append(thead);

    const tbody = el("tbody");
    const list = el("div", "m-list");
    for (const [facade, covers] of this._grouped()) {
      if (!covers.length) continue;
      const facName = facade ? `${T.facade} ${facade}` : T.noFacade;
      const fr = el("tr", "facade");
      const fth = el("th");
      const fl = el("div", "fl");
      fl.append(icon("mdi:compass-outline"), document.createTextNode(facName));
      fth.append(fl);
      fr.append(fth);
      const fd = el("td");
      fd.colSpan = this._cfg.modes.length;
      fr.append(fd);
      tbody.append(fr);
      list.append(el("div", "grp-h", facName));

      for (const cover of covers) {
        // One line per cover: its template is on its own page, not here.
        const tr = el("tr");
        const th = el("th");
        const rowh = el("div", "rowh");
        rowh.append(this._coverPic(cover));
        const nm = el("span", "nm", this._coverName(cover));
        nm.title = cover.template ? `${T.template} ${cover.template}` : T.noTemplate;
        rowh.append(nm);
        th.append(rowh);
        tr.append(th);
        // The same cover on a phone: its modes two by two, under its name.
        const card = el("section", "card m-card");
        card.append(el("div", "nm", this._coverName(cover)));
        const items = el("div", "m-cells");
        for (const mode of this._cfg.modes) {
          const td = el("td", "cell");
          td.append(this._cellNode(cover, mode));
          tr.append(td);
          const item = el("div", "m-item");
          const lab = el("span", "m-lab");
          const dot = el("span", "dot");
          dot.style.background = mode.color || "#888888";
          lab.append(dot, el("span", "", mode.name));
          item.append(lab, this._cellNode(cover, mode));
          items.append(item);
        }
        tbody.append(tr);
        card.append(items);
        list.append(card);
      }
    }
    table.append(tbody);
    scroll.append(table);
    box.append(scroll, list);
    wrap.append(box);
    this._matrixScroll = scroll;
  }

  _cellNode(cover, mode, onApply = null) {
    const cfg = (cover.modes || {})[mode.name];
    const linked = cfg !== undefined;
    const kind = cfgKind(cfg);
    let cv;
    if (!linked) {
      // Empty stays quiet: a dot, and the "+" under the pointer or the focus.
      cv = el("div", "cv empty");
      cv.title = T.linkMode;
      cv.append(icon("mdi:plus"));
    } else if (kind === "fixed") {
      // A fixed position in a mode that computes is an override: marked so.
      cv = el("div", `cv fixed${mode.behavior ? " ovr" : ""}`);
      const gauge = el("span", "gauge");
      const fill = el("i");
      fill.style.width = `${cfg.value}%`;
      gauge.append(fill);
      cv.append(gauge, document.createTextNode(String(cfg.value)), el("small", "pct", "%"));
      if (mode.behavior) cv.title = T.overrideTitle;
    } else if (kind === "entity") {
      cv = el("div", `cv entity${mode.behavior ? " ovr" : ""}`);
      cv.append(icon("mdi:link-variant"),
        document.createTextNode(String(cfg.value).split(".").pop().slice(0, 12)));
      cv.title = mode.behavior ? `${T.overrideTitle}\n${cfg.value}` : cfg.value;
    } else {
      // Three different meanings shared one primary blue: "no forced position"
      // (plain mode), "computed by shading", "computed by solar gain". The tint
      // now comes from the mode's own colour — the same one its header icon
      // already wears — so a column reads as one object top to bottom.
      // The label keeps --primary-text-color: a mode set to #FFFFFF would make
      // its own text vanish on a light theme. It says "auto" only where a
      // position is computed; a plain mode's cell says there is none.
      cv = el("div", "cv auto");
      const tint = mode.color || "var(--primary-color)";
      cv.style.background = `color-mix(in srgb, ${tint} 14%, transparent)`;
      cv.append(behaviorBadge(mode.behavior), el("span", "", mode.behavior ? T.auto : T.noTarget));
    }
    cv.setAttribute("role", "button");
    cv.tabIndex = 0;
    const open = () => this._openPopover(cv, cover, mode, onApply);
    cv.addEventListener("click", open);
    cv.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } });
    return cv;
  }

  /* ---------- popover editor ---------- */

  _closePopover() {
    if (this._reanchor) {
      window.removeEventListener("resize", this._reanchor);
      this._matrixScroll?.removeEventListener("scroll", this._reanchor);
      this.removeEventListener("scroll", this._reanchor);
      this._reanchor = null;
    }
    if (this._onEsc) {
      this.shadowRoot.removeEventListener("keydown", this._onEsc);
      this._onEsc = null;
    }
    this.shadowRoot.querySelectorAll(".pop, .backdrop").forEach((n) => n.remove());
    this._pop = null;
    // The popover's ha-selector just left the tree; drop it from the cache the
    // hass setter iterates, so it stops writing to a detached node.
    this._trackLiveNodes();
  }

  /** Glue the popover to its cell, clamped to the viewport (flips above when
      there is no room below). Called on open and on every scroll/resize. */
  _anchorPopover() {
    const st = this._pop;
    if (!st?.popEl || !st.anchorEl?.isConnected) return;
    const M = 8;
    const pop = st.popEl;
    const ab = st.anchorEl.getBoundingClientRect();
    const pw = pop.offsetWidth;
    const ph = pop.offsetHeight;

    let left = Math.min(ab.left, window.innerWidth - pw - M);
    left = Math.max(M, left);

    let top = ab.bottom + 6;
    if (top + ph > window.innerHeight - M) {
      const above = ab.top - ph - 6;
      top = above >= M ? above : Math.max(M, window.innerHeight - ph - M);
    }
    pop.style.left = `${left}px`;
    pop.style.top = `${top}px`;
  }

  /**
   * The editor of one cell. From the matrix it saves at once; from a cover's
   * editor, *onApply* gets the value instead (null to remove the mode) and
   * the cover's own save bar keeps the last word.
   */
  async _openPopover(anchor, cover, mode, onApply = null) {
    this._closePopover();
    const cfg = (cover.modes || {})[mode.name];
    const linked = cfg !== undefined;
    const isBehavior = mode.behavior === "auto_shade" || mode.behavior === "solar_gain";

    const state = {
      choice: cfgKind(cfg),                       // fixed | entity | none
      fixed: cfgKind(cfg) === "fixed" ? Number(cfg.value) : 50,
      entity: cfgKind(cfg) === "entity" ? cfg.value : null,
      applyFacade: false,
      selectorEl: null,
      anchorEl: null,
      popEl: null,
    };
    this._pop = state;

    const backdrop = el("div", "backdrop");
    backdrop.addEventListener("click", () => this._closePopover());
    const pop = el("div", "pop");
    pop.setAttribute("role", "dialog");
    pop.setAttribute("aria-modal", "true");
    pop.setAttribute("aria-label", T.posTitle(mode.name, this._coverName(cover)));

    pop.append(el("h4", "", T.posTitle(mode.name, this._coverName(cover))));

    const body = el("div");
    pop.append(body);

    // In a cover's editor the draft is one cover: its neighbours are not in it.
    const facadeMates = onApply ? [] : this._cfg.covers.filter(
      (c) => c !== cover && c.facade === cover.facade && cover.facade
    );

    const renderBody = () => {
      body.replaceChildren();
      body.append(el("p", "sub", isBehavior ? T.behaviorSub[mode.behavior] : T.posSub));
      const seg = el("div", "seg");
      // On a behavior mode the "no value" choice does not mean "no position"
      // but "computed" - same stored shape ({type:"auto"}), other label, and it
      // comes first because it is the default. Fixed/entity become a per-cover
      // override of the computation.
      const segs = isBehavior
        ? [["none", T.segAuto], ["fixed", T.segFixed], ["entity", T.segEntity]]
        : [["fixed", T.segFixed], ["entity", T.segEntity], ["none", T.segNone]];
      for (const [key, label] of segs) {
        const b = el("button", state.choice === key ? "on" : "", label);
        b.addEventListener("click", () => { state.choice = key; renderBody(); });
        seg.append(b);
      }
      body.append(seg);

      if (isBehavior && state.choice !== "none") {
        body.append(el("p", "hint", T.overrideHint));
      }
      if (state.choice === "fixed") {
        const row = el("div", "pos-slider");
        const range = document.createElement("input");
        range.type = "range"; range.min = "0"; range.max = "100"; range.value = String(state.fixed);
        paintRange(range);
        const val = el("span", "val", `${state.fixed} %`);
        range.addEventListener("input", () => {
          state.fixed = Number(range.value);
          val.textContent = `${state.fixed} %`;
          paintRange(range);
        });
        row.append(range, val);
        body.append(row);
      } else if (state.choice === "entity") {
        body.append(el("p", "hint", T.entityHint));
        const sel = document.createElement("ha-selector");
        sel.hass = this._hass;
        sel.selector = { entity: { domain: ["input_number", "number"] } };
        sel.value = state.entity || undefined;
        sel.addEventListener("value-changed", (e) => { state.entity = e.detail.value; });
        state.selectorEl = sel;
        body.append(sel);
      } else {
        body.append(el("p", "hint", isBehavior ? T.autoHint : T.noneHint));
      }

      if (facadeMates.length) {
        const lbl = el("label", "apply-row");
        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.checked = state.applyFacade;
        cb.addEventListener("change", () => { state.applyFacade = cb.checked; });
        lbl.append(cb, document.createTextNode(
          facadeMates.length === 1
            ? T.applyFacadeOne(this._coverName(facadeMates[0]), cover.facade)
            : T.applyFacade(facadeMates.length, cover.facade)
        ));
        body.append(lbl);
      }
      // Switching segment changes the height a lot (the entity picker is tall):
      // re-clamp so the popover never overflows the viewport. No-op before mount.
      this._anchorPopover();
    };

    // ha-selector needs the editor chunk; load it before first entity render.
    await loadHaForm();
    renderBody();

    const actions = el("div", "actions");
    const done = (value, btn) => {
      if (!onApply) { this._commit(cover, mode, value, state, btn); return; }
      this._closePopover();
      onApply(value);
    };
    if (linked) {
      const unlink = el("button", "btn danger");
      unlink.append(icon("mdi:link-variant-off"), document.createTextNode(T.unlink));
      unlink.addEventListener("click", () => done(null, unlink));
      actions.append(unlink);
    }
    actions.append(el("span", "spacer"));
    const cancel = el("button", "btn ghost", T.cancel);
    cancel.addEventListener("click", () => this._closePopover());
    const save = el("button", "btn primary", onApply ? T.applyDraft : linked || !isBehavior ? T.save : T.link);
    save.addEventListener("click", () => {
      let value;
      if (state.choice === "none") value = { type: "auto" };
      else if (state.choice === "fixed") value = { type: "fixed", value: Math.round(state.fixed) };
      else if (state.entity) value = { type: "entity", value: state.entity };
      else value = { type: "auto" };
      done(value, save);
    });
    actions.append(cancel, save);
    pop.append(actions);

    // Mounted on the shadow root, NOT in .m-scroll: a fixed-position overlay
    // cannot be clipped by the matrix box nor extend its scrollable area.
    state.anchorEl = anchor;
    state.popEl = pop;
    this.shadowRoot.append(backdrop, pop);
    this._anchorPopover();

    // The anchor moves with the matrix and the page, so re-anchor on scroll.
    this._reanchor = () => this._anchorPopover();
    window.addEventListener("resize", this._reanchor);
    this._matrixScroll?.addEventListener("scroll", this._reanchor, { passive: true });
    this.addEventListener("scroll", this._reanchor, { passive: true });

    // A dialog the tab key can walk out of is not a dialog: without this, Tab
    // leaves for the matrix that the backdrop has just made unreachable to the
    // mouse. Escape still closes.
    const focusables = () => [...pop.querySelectorAll(FOCUSABLE)].filter(
      (n) => !n.hasAttribute("disabled")
    );
    this._onEsc = (e) => {
      if (e.key === "Escape") { e.stopPropagation(); this._closePopover(); return; }
      if (e.key !== "Tab") return;
      const f = focusables();
      if (!f.length) return;
      const active = this.shadowRoot.activeElement;
      const first = f[0], last = f[f.length - 1];
      if (e.shiftKey && (active === first || !pop.contains(active))) {
        e.preventDefault(); last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault(); first.focus();
      }
    };
    this.shadowRoot.addEventListener("keydown", this._onEsc);
    focusables()[0]?.focus();

    // The popover mounts its own ha-selector outside the render pass.
    this._trackLiveNodes();
  }

  /** value: mode cfg object to store, or null to unlink. */
  async _commit(cover, mode, value, state, btn) {
    const items = this._cfg.covers.map((c) => ({ ...c, modes: { ...(c.modes || {}) } }));
    const targets = [cover];
    if (state.applyFacade && value !== null) {
      targets.push(...this._cfg.covers.filter(
        (c) => c !== cover && c.facade === cover.facade && cover.facade
      ));
    }
    for (const t of targets) {
      const item = items[this._cfg.covers.indexOf(t)];
      if (value === null) delete item.modes[mode.name];
      else item.modes[mode.name] = value;
    }
    // The popover stays up until the server has accepted. Closing first meant a
    // rejected save left the user with a toast and nothing to correct — the
    // slider, the entity and the "apply to the facade" tick were all gone.
    // _saveCovers re-renders on success, and _render closes the popover anyway.
    const label = btn?.textContent;
    if (btn) { btn.disabled = true; btn.textContent = T.saving; }
    try {
      await this._saveCovers(items);
    } catch (err) {
      console.error(`${DOMAIN}: save failed`, err);
      toast(this, wsError(err));
      if (btn) { btn.disabled = false; btn.textContent = label; }
    }
  }

  /* ---------- shared editor plumbing ---------- */

  /** Persist one section, re-read the truth, close the editor. */
  async _saveSection(section, items) {
    try {
      await this._hass.connection.sendMessagePromise({
        type: WS_SAVE, section, data: items,
      });
      this._cfg = await this._hass.connection.sendMessagePromise({ type: WS_GET });
      // Both drafts die here, and BEFORE the re-render: the server normalises
      // what it stores (clamps, drops blanks, packs templates), so showing the
      // draft again would show values that are no longer what is saved.
      this._edit = null;
      this._globalDraft = null;
      this._globalClean = null;
      this._schedDraft = null;
      this._schedClean = null;
      this._render();
      toast(this, T.saved);
      return true;
    } catch (err) {
      console.error(`${DOMAIN}: save ${section} failed`, err);
      toast(this, wsError(err));
      return false;
    }
  }

  /** How many covers link each mode. */
  _usage() {
    const out = {};
    for (const c of this._cfg.covers) {
      for (const name of Object.keys(c.modes || {})) out[name] = (out[name] || 0) + 1;
    }
    return out;
  }

  _templateOf(item) {
    return this._cfg.templates.find((t) => t.name === item.template) || null;
  }

  /**
   * Values a template imposes. Templates arrive already flattened by the server
   * (_flatten_template), every behavior field filled in — so this is a pick, not
   * a second copy of the defaults table.
   */
  _templateDefaults(tpl) {
    if (!tpl) return {};
    const out = {};
    for (const name of Object.keys(this._cfg.behavior?.fields || {})) {
      if (Object.prototype.hasOwnProperty.call(tpl, name)) out[name] = tpl[name];
    }
    return out;
  }

  /** The value a field actually takes: cover override, else template, else default. */
  _baseline(draft) {
    const fields = this._cfg.behavior?.fields || {};
    const base = {};
    for (const [name, spec] of Object.entries(fields)) base[name] = spec.default;
    return { ...base, ...this._templateDefaults(this._templateOf(draft)) };
  }

  /* ---------- editor building blocks ---------- */

  /** A card that answers one question: icon, title, one line under it. */
  _edCard(iconName, title, sub) {
    const card = el("section", "card ed-card");
    const h = el("h3");
    h.append(icon(iconName), el("span", "", title));
    card.append(h);
    if (sub) card.append(el("p", "ed-sub", sub));
    return card;
  }

  /** A label above its control. */
  _labeled(label, control, cls = "") {
    const box = el("div", cls);
    box.append(el("span", "ed-lbl", label), control);
    return box;
  }

  _edInput(value, onInput, cls = "", placeholder = "") {
    const input = document.createElement("input");
    input.type = "text";
    input.className = `ed-input ${cls}`.trim();
    input.value = value ?? "";
    if (placeholder) input.placeholder = placeholder;
    input.addEventListener("input", () => onInput(input.value));
    return input;
  }

  _edSelect(value, options, onChange, cls = "") {
    const sel = document.createElement("select");
    sel.className = `ed-select ${cls}`.trim();
    for (const [val, text] of options) {
      const o = document.createElement("option");
      o.value = val === null ? "" : String(val);
      o.textContent = text;
      if ((value ?? "") === (val ?? "")) o.selected = true;
      sel.append(o);
    }
    sel.addEventListener("change", () => onChange(sel.value || null));
    return sel;
  }

  /** A bare HA selector (entity, icon…), without the row around it. */
  _haSelector(selector, value, onChange, label) {
    const sel = document.createElement("ha-selector");
    sel.hass = this._hass;
    sel.selector = selector;
    sel.value = value ?? undefined;
    if (label) sel.label = label;
    sel.addEventListener("value-changed", (e) => onChange(e.detail.value));
    return sel;
  }

  /** A switch the keyboard and screen readers know as one. */
  _switch(checked, onChange, label) {
    const b = el("button", "tsw");
    b.type = "button";
    b.setAttribute("role", "switch");
    b.setAttribute("aria-checked", String(!!checked));
    if (label) b.setAttribute("aria-label", label);
    b.addEventListener("click", () => {
      const v = b.getAttribute("aria-checked") !== "true";
      b.setAttribute("aria-checked", String(v));
      onChange(v);
    });
    return b;
  }

  /** Icon tile, label, one line, switch. The tile lights up with the switch. */
  _optRow(iconName, label, hint, value, onChange) {
    const row = el("div", "opt");
    const tile = el("span", `tile${value ? " on" : ""}`);
    tile.append(icon(iconName));
    const txt = el("div", "txt");
    txt.append(el("div", "t", label));
    if (hint) txt.append(el("div", "h", hint));
    row.append(tile, txt, this._switch(value, (v) => {
      tile.classList.toggle("on", v);
      onChange(v);
    }, label));
    return row;
  }

  /** The (i) whose tooltip holds the detail a one-line hint leaves out. */
  _info(text) {
    const i = icon("mdi:information-outline", "info");
    i.title = text;
    i.setAttribute("role", "img");
    i.setAttribute("aria-label", text);
    return i;
  }

  _note(text) {
    const p = el("p", "ed-note");
    p.append(icon("mdi:information-outline"), el("span", "", text));
    return p;
  }

  /** A note that something will not save as it stands. */
  _warnNote(text) {
    const p = el("p", "ed-note warn");
    p.append(icon("mdi:alert-outline"), el("span", "", text));
    return p;
  }

  /** The delete button, and why it is off when it is: said, not hidden in a tooltip. */
  _deleteButton(used, reason, onDelete) {
    const out = [];
    const del = el("button", "btn danger");
    del.append(icon("mdi:delete-outline"), document.createTextNode(T.delete));
    if (used) {
      del.disabled = true;
      del.title = reason;
      out.push(del, el("span", "why", reason));
    } else {
      del.addEventListener("click", onDelete);
      out.push(del);
    }
    return out;
  }

  /**
   * The one save bar of every editor. Nothing to save, nothing to show: the
   * bar keeps only Delete, at the end of the page, or disappears. The first
   * change sticks it to the bottom of the screen with what is pending, Cancel
   * and Save, and marks the tab; undoing the last one puts it away again.
   * _syncSaveBar compares the drafts with their snapshots after every edit,
   * wherever it came from.
   */
  _saveBar(onSave, del = null) {
    const bar = el("div", `actions card savebar${del ? "" : " bare"}`);
    if (del) bar.append(...this._deleteButton(del.used || 0, del.reason || "", del.onDelete));
    const pending = el("span", "pending");
    pending.append(el("span", "dot"), el("span", "ptext", T.unsaved));
    const cancel = el("button", "btn ghost", T.cancel);
    cancel.type = "button";
    cancel.addEventListener("click", () => { if (this._leaveEditor()) this._render(); });
    const save = el("button", "btn primary", T.save);
    save.type = "button";
    save.addEventListener("click", onSave);
    bar.append(el("span", "spacer"), pending, cancel, save);
    this._syncSaveBar = () => {
      const dirty = this._dirty();
      save.disabled = !dirty;
      cancel.disabled = !dirty;
      pending.hidden = !dirty;
      bar.classList.toggle("dirty", dirty);
      this._tabBtn?.classList.toggle("dirty", dirty);
    };
    return bar;
  }

  /** The cover's facade. Changing it redraws the editor, whose sketches and
   *  angle hints depend on it. */
  _facadeField(draft, rerender) {
    const sel = this._edSelect(draft.facade,
      this._cfg.facades.map((f) => [f.name,
        [f.name, `${facadeAzimuth(f)}°`, T.slopeShort(facadeTilt(f))].filter(Boolean).join(" · ")]),
      (v) => { draft.facade = v; rerender(); });
    return this._labeled(T.facade, sel);
  }

  /** The cover's template. Only those made for its facade's type of window are
   *  offered; one of another type already chosen stays, named with its type,
   *  for the warning under it to make sense. */
  _templateField(draft, rerender) {
    const facKind = tiltKind(facadeTilt(this._cfg.facades.find((f) => f.name === draft.facade)));
    const offered = this._cfg.templates.filter((t) => templateKind(t) === facKind || t.name === draft.template);
    const sel = this._edSelect(draft.template,
      [[null, T.noTemplateOpt], ...offered.map((t) => [t.name,
        templateKind(t) === facKind ? t.name : `${t.name} (${T.slopeKinds[templateKind(t)].toLowerCase()})`])],
      (v) => { draft.template = v; rerender(); });
    return this._labeled(T.templateTitle, sel);
  }

  /**
   * The slope the behavior editor works with. A cover has its facade's: a
   * wall stops the angles at 90° and the heights at the zenith, a roof opens
   * the angles to 180° and the heights down to the roof. A template has its
   * own window type; a roof's is drawn on the flattest roof of the house,
   * whose heights reach the furthest (30° when the house has none).
   */
  _slope(draft) {
    const geo = (tilt, template, refFromHouse = false) => {
      const kind = tiltKind(tilt);
      return { tilt, kind, angleMax: kind === "wall" ? 90 : 180, heightMax: heightLimit(tilt), template, refFromHouse };
    };
    if (this._edit?.section !== "template") {
      return geo(facadeTilt(this._cfg.facades.find((f) => f.name === draft.facade)), false);
    }
    const kind = templateKind(draft);
    if (kind !== "roof") return geo(kind === "wall" ? 90 : 0, true);
    const roofs = this._cfg.facades.map(facadeTilt).filter((t) => tiltKind(t) === "roof");
    return roofs.length ? geo(Math.min(...roofs), true, true) : geo(30, true);
  }

  /** Entities as chips with their live state, and one picker to add another. */
  _entityChips(list, onChange) {
    const box = el("div");
    const chips = el("div", "ents");
    const st = this._hass.states;
    for (const eid of list) {
      const chip = el("span", "ent");
      const name = el("span");
      name.append(document.createTextNode(st[eid]?.attributes?.friendly_name || eid), el("span", "eid", eid));
      chip.append(name);
      const s = st[eid];
      if (s) {
        const shown = this._hass.formatEntityState ? this._hass.formatEntityState(s) : s.state;
        chip.append(el("span", `st${s.state === "on" ? " on" : ""}`, shown));
      }
      const rm = el("button");
      rm.type = "button";
      rm.title = T.removeEntity;
      rm.setAttribute("aria-label", `${T.removeEntity} ${eid}`);
      rm.append(icon("mdi:close"));
      rm.addEventListener("click", () => onChange(list.filter((e) => e !== eid)));
      chip.append(rm);
      chips.append(chip);
    }
    box.append(chips, this._haSelector({ entity: {} }, undefined, (v) => {
      if (v && !list.includes(v)) onChange([...list, v]);
    }, T.addEntity));
    return box;
  }

  /**
   * One behavior number: a typed box and its unit, one hint line, a short
   * slider. The value shown is always the EFFECTIVE one. Under a template the
   * row says where that value comes from: inherited, it sits in a dashed grey
   * box with a link; overridden, it turns amber, recalls the template's value
   * (also marked on the slider) and offers the way back.
   * `tplName` is the template's name, or null when there is none to inherit.
   */
  _behaviorRow(name, spec, draft, baseline, tplName, onValue, hintText, labelText) {
    const has = (k) => Object.prototype.hasOwnProperty.call(draft, k);
    const num = new Intl.NumberFormat(LANG, { maximumFractionDigits: 2 });
    const fmt = (v) => `${num.format(v)}${spec.unit ? ` ${spec.unit}` : ""}`;
    const round = (raw) => (spec.step && spec.step < 1 ? Math.round(raw * 10) / 10 : Math.round(raw));
    const clamp = (n) => Math.min(spec.max, Math.max(spec.min, n));
    const row = el("div", "numf");
    const t = el("div", "t");
    const label = labelText || T.fields[name] || name;
    t.append(el("span", "", label));
    const hint = el("div", "h", hintText || T.fieldHints?.[name] || "");
    row.append(t, hint);

    const box = document.createElement("input");
    box.type = "number";
    box.min = String(spec.min);
    box.max = String(spec.max);
    box.step = String(spec.step || 1);
    box.setAttribute("aria-label", label);
    const val = el("div", "val");
    val.append(box, el("span", "u", spec.unit || ""));
    row.append(val);

    const rwrap = el("div", "rwrap");
    const range = document.createElement("input");
    range.type = "range";
    range.min = String(spec.min);
    range.max = String(spec.max);
    range.step = String(spec.step || 1);
    range.tabIndex = -1;  // the box is the keyboard's way in; one stop per field
    range.setAttribute("aria-hidden", "true");
    rwrap.append(range);
    row.append(rwrap);

    // Built once and merely hidden, never re-created: rebuilding the row on the
    // first slider move would tear the input out from under the pointer and
    // abort the drag. Without a template there is nothing to revert TO, so the
    // affordance stays out of the way entirely.
    let reset = null;
    if (tplName) {
      // Overridden: one line under the slider says so, recalls the template's
      // value (also marked on the track) and offers the way back.
      reset = this._overrideLine(row, fmt(baseline[name]));
      const ghost = el("span", "ghost");
      ghost.style.left = `${((baseline[name] - spec.min) / ((spec.max - spec.min) || 1)) * 100}%`;
      rwrap.append(ghost);
    }

    const show = (v) => { box.value = String(v); range.value = String(v); paintRange(range); };
    const mark = (on) => {
      if (!tplName) return;
      row.classList.toggle("ovr", on);
      row.classList.toggle("inh", !on);
      box.title = on ? "" : T.inheritedTitle(tplName);
    };
    const set = (n, from) => {
      draft[name] = n;
      if (from !== box) box.value = String(n);
      if (from !== range) range.value = String(n);
      paintRange(range);
      mark(true);
      onValue?.();
    };
    show(has(name) ? draft[name] : baseline[name]);
    mark(has(name));

    range.addEventListener("input", () => set(round(Number(range.value)), range));
    box.addEventListener("input", () => {
      // An empty box is a transient state while typing, not a zero.
      if (box.value === "" || !Number.isFinite(Number(box.value))) return;
      set(clamp(round(Number(box.value))), box);
    });
    box.addEventListener("change", () => show(has(name) ? draft[name] : baseline[name]));
    reset?.addEventListener("click", () => {
      delete draft[name];
      show(baseline[name]);
      mark(false);
      onValue?.();
    });
    return row;
  }

  /** What an overridden value shows under its slider: the word, the
   *  template's value and the way back. Hidden while the value is inherited.
   *  Returns the way back. */
  _overrideLine(row, tplText) {
    const line = el("div", "oline");
    const reset = el("button", "revert backtpl");
    reset.type = "button";
    reset.title = T.revertTitle;
    reset.append(icon("mdi:undo-variant"), document.createTextNode(T.backToTpl));
    line.append(el("span", "olab", T.ovrLabel), el("span", "from", T.fromTemplate(tplText)), reset);
    row.append(line);
    return reset;
  }

  /**
   * Minimum and maximum sun height: one range, two thumbs, two boxes. Past a
   * wall's 90° the range goes on over the zenith, down the far side of a roof
   * (see shade.sun_height): the zenith is marked on the track.
   */
  _elevationRow(lo, hi, specs, draft, baseline, tplName, onValue) {
    const over = specs[hi].max > 90;
    const v = (k) => Math.min(specs[k].max, baseline[k]);
    return this._dualRow(lo, hi, specs, draft, baseline, tplName, onValue, {
      title: T.elevationRange, hint: over ? T.elevationHintRoof : T.elevationHint, sep: T.rangeTo,
      tpl: `${v(lo)} ${T.rangeTo} ${v(hi)} ${specs[lo].unit}`,
      ...(over ? { axisAt: 90, ends: [T.elevEnds[0], { text: T.elevEnds[1], at: 90 }, T.elevEnds[2]] } : {}),
    });
  }

  /**
   * The angles to the left and to the right: one track centred on the window's
   * axis, as seen from inside looking out. The left thumb moves over the left
   * half, the right one over the right half, and the fill between them is the
   * sector.
   */
  _sectorRow(lo, hi, specs, draft, baseline, tplName, onValue) {
    const u = specs[lo].unit;
    const v = (k) => Math.min(specs[k].max, baseline[k]);
    return this._dualRow(lo, hi, specs, draft, baseline, tplName, onValue, {
      title: T.sectorRange, hint: T.sectorHint, sep: u, sector: true,
      tpl: `${v(lo)} ${u} | ${v(hi)} ${u}`,
      ends: T.sectorEnds,
    });
  }

  /**
   * Two numbers on one track, two thumbs, two boxes. A range (`sector` false)
   * keeps lo <= hi. A sector puts lo to the left of a middle axis, counted
   * outwards, and hi to its right. A value stored past what this window allows
   * (a roof's 180° on a wall) is shown at the limit and kept until edited.
   */
  _dualRow(lo, hi, specs, draft, baseline, tplName, onValue, o) {
    const has = (k) => Object.prototype.hasOwnProperty.call(draft, k);
    const cur = (k) => Math.min(specs[k].max, has(k) ? draft[k] : baseline[k]);
    const spec = specs[lo];
    const mid = o.sector ? specs[lo].max : 0;
    const tMin = o.sector ? 0 : spec.min;
    const tMax = o.sector ? specs[lo].max + specs[hi].max : spec.max;
    // Value <-> place on the track.
    const toPos = (k, v) => (!o.sector ? v : k === lo ? mid - v : mid + v);
    const fromPos = (k, p) => (!o.sector ? p : k === lo ? mid - p : p - mid);
    const clampK = (k, n) => Math.min(specs[k].max, Math.max(specs[k].min, n));
    const row = el("div", "numf");
    const t = el("div", "t");
    t.append(el("span", "", o.title));
    const hint = el("div", "h", o.hint);
    row.append(t, hint);

    const mkBox = (k) => {
      const b = document.createElement("input");
      b.type = "number";
      b.min = String(specs[k].min);
      b.max = String(specs[k].max);
      b.step = String(specs[k].step || 1);
      b.setAttribute("aria-label", T.fields[k] || k);
      return b;
    };
    const boxes = { [lo]: mkBox(lo), [hi]: mkBox(hi) };
    const val = el("div", "val");
    val.append(boxes[lo], el("span", "u", o.sep), boxes[hi], el("span", "u", spec.unit || ""));
    row.append(val);

    const dual = el("div", "dual");
    const track = el("div", "track");
    const fill = el("i");
    track.append(fill);
    const axisAt = o.sector ? mid : o.axisAt;
    if (axisAt != null) {
      const axis = el("b", "axis");
      axis.style.left = `${((axisAt - tMin) / ((tMax - tMin) || 1)) * 100}%`;
      track.append(axis);
    }
    dual.append(track);
    const ranges = {};
    for (const k of [lo, hi]) {
      const r = document.createElement("input");
      r.type = "range";
      r.min = String(tMin);
      r.max = String(tMax);
      r.step = String(specs[k].step || 1);
      r.tabIndex = -1;
      r.setAttribute("aria-hidden", "true");
      ranges[k] = r;
      dual.append(r);
    }
    row.append(dual);
    if (o.ends) {
      // A word with `at` sits under that value (the zenith), the others spread.
      const ends = el("div", "ends");
      for (const w of o.ends) {
        if (typeof w === "string") { ends.append(el("span", "", w)); continue; }
        const at = el("span", "at", w.text);
        at.style.left = `${((w.at - tMin) / ((tMax - tMin) || 1)) * 100}%`;
        ends.append(at);
      }
      row.append(ends);
    }
    const reset = tplName ? this._overrideLine(row, o.tpl) : null;

    const paint = () => {
      for (const k of [lo, hi]) { boxes[k].value = String(cur(k)); ranges[k].value = String(toPos(k, cur(k))); }
      const span = tMax - tMin || 1;
      const a = toPos(lo, cur(lo)), b = toPos(hi, cur(hi));
      fill.style.left = `${((Math.min(a, b) - tMin) / span) * 100}%`;
      fill.style.width = `${(Math.abs(b - a) / span) * 100}%`;
    };
    const mark = () => {
      if (!tplName) return;
      const on = has(lo) || has(hi);
      row.classList.toggle("ovr", on);
      row.classList.toggle("inh", !on);
      for (const k of [lo, hi]) boxes[k].title = on ? "" : T.inheritedTitle(tplName);
    };
    // A range's thumbs never cross: each one stops at the other. A sector's
    // stop at the axis, each on its own side.
    const set = (k, n) => {
      n = clampK(k, n);
      draft[k] = o.sector ? n : k === lo ? Math.min(n, cur(hi)) : Math.max(n, cur(lo));
      paint();
      mark();
      onValue?.();
    };
    for (const k of [lo, hi]) {
      ranges[k].addEventListener("input", () => set(k, fromPos(k, Math.round(Number(ranges[k].value)))));
      boxes[k].addEventListener("input", () => {
        if (boxes[k].value === "" || !Number.isFinite(Number(boxes[k].value))) return;
        set(k, Math.round(Number(boxes[k].value)));
      });
      boxes[k].addEventListener("change", paint);
    }
    reset?.addEventListener("click", () => { delete draft[lo]; delete draft[hi]; paint(); mark(); onValue?.(); });
    paint();
    mark();
    return row;
  }

  /**
   * Side view of the window, drawn to scale from the three geometry numbers:
   * the opening between the minimum and maximum heights, and the cover lowered
   * just enough for a sun 40° high to light the floor up to the distance. The
   * scale shrinks to keep a tall window or a long distance inside the sketch.
   */
  _figGeometry(draft, baseline, geo) {
    if (geo?.kind === "roof") return this._figGeometrySloped(draft, baseline, geo.tilt);
    const F = T.fig;
    const box = el("div", "fig");
    box.style.color = "var(--secondary-text-color)";
    box.innerHTML = `<span class="cap"></span><svg viewBox="0 0 170 152" aria-hidden="true">
      <rect class="wall" x="52" y="4" width="8" fill="currentColor" fill-opacity=".25"/>
      <rect class="glass" x="52" width="8" fill="var(--card-background-color)" stroke="currentColor" stroke-opacity=".45" stroke-dasharray="2 2"/>
      <rect class="cover" x="52" width="8" fill="var(--primary-color)" opacity=".85"/>
      <line x1="0" y1="128" x2="170" y2="128" stroke="currentColor" stroke-opacity=".45" stroke-width="2"/>
      <circle class="sun" r="7" fill="var(--ce-b-shade)"/>
      <line class="ray-out" stroke="var(--ce-b-shade)" stroke-width="1.5"/>
      <line class="ray-in" stroke="var(--ce-b-shade)" stroke-width="1.5" stroke-dasharray="4 2"/>
      <line class="dist" y1="137" y2="137" stroke="var(--fp-warn)" stroke-width="1.5"/>
      <line class="dist-a" y1="133" y2="141" stroke="var(--fp-warn)" stroke-width="1.5"/>
      <line class="dist-b" y1="133" y2="141" stroke="var(--fp-warn)" stroke-width="1.5"/>
      <line class="tick-max" x1="62" x2="70" stroke="currentColor" stroke-opacity=".6"/>
      <line class="tick-min" x1="62" x2="70" stroke="currentColor" stroke-opacity=".6"/>
      <text class="t-dist" y="150" fill="var(--fp-warn)" text-anchor="middle"></text>
      <text class="t-max" x="73" fill="currentColor"></text>
      <text class="t-min" x="73" fill="currentColor"></text>
      <text x="166" y="122" fill="currentColor" fill-opacity=".6" text-anchor="end"></text>
      <text x="4" y="122" fill="currentColor" fill-opacity=".6"></text>
    </svg>`;
    const $ = (sel) => box.querySelector(sel);
    $(".cap").textContent = F.section;
    const texts = box.querySelectorAll("text");
    // Words go in as text, never as markup.
    texts[3].textContent = F.room;
    texts[4].textContent = F.outside;
    const set = (sel, attrs) => { for (const [k, v] of Object.entries(attrs)) $(sel).setAttribute(k, String(Math.round(v * 10) / 10)); };
    const num = new Intl.NumberFormat(LANG, { maximumFractionDigits: 2 });
    const cur = (k) => Number(Object.prototype.hasOwnProperty.call(draft, k) ? draft[k] : baseline[k]);
    const FLOOR = 128, WALL = 52, IN = 60, TAN = Math.tan(toRad(40));

    box.redraw = () => {
      const d = Math.max(0, cur("shade_distance"));
      const hi = Math.max(0, cur("shade_max_height"));
      const lo = Math.min(Math.max(0, cur("shade_min_height")), hi);
      // Pixels per metre: as large as fits, the window under the top margin
      // and the lit floor inside the room.
      const k = Math.min(42, (FLOOR - 18) / Math.max(hi, 0.3), 100 / Math.max(d, 0.05));
      const yTop = FLOOR - hi * k;
      const ySill = FLOOR - lo * k;
      // The cover's bottom edge: where a 40° ray grazing it lands at the distance,
      // held between the closed and the open positions like the real computation.
      const hb = Math.min(hi, Math.max(lo, d * TAN));
      const yB = FLOOR - hb * k;
      const hit = IN + (hb / TAN) * k;
      set(".wall", { height: FLOOR - 4 });
      set(".glass", { y: yTop, height: Math.max(ySill - yTop, 0) });
      set(".cover", { y: yTop, height: Math.max(yB - yTop, 0) });
      // Outside, the ray climbs back towards the sun at the same 40°.
      const sx = Math.max(10, WALL - Math.min(44, (yB - 10) / TAN));
      const sy = yB - (WALL - sx) * TAN;
      set(".sun", { cx: sx, cy: sy });
      set(".ray-out", { x1: sx, y1: sy, x2: WALL, y2: yB });
      set(".ray-in", { x1: IN, y1: yB, x2: hit, y2: FLOOR });
      const end = IN + d * k;
      set(".dist", { x1: IN, x2: end });
      set(".dist-a", { x1: IN, x2: IN });
      set(".dist-b", { x1: end, x2: end });
      set(".t-dist", { x: Math.min(140, Math.max(40, (IN + end) / 2)) });
      texts[0].textContent = `${F.distance} ${num.format(d)} m`;
      // Two labels on the inner face of the wall; kept apart when the window is short.
      const yMaxT = Math.max(12, yTop + 3);
      const yMinT = Math.min(FLOOR - 9, Math.max(ySill - 2, yMaxT + 11));
      set(".tick-max", { y1: yTop, y2: yTop });
      set(".tick-min", { y1: ySill, y2: ySill });
      set(".t-max", { y: yMaxT });
      set(".t-min", { y: yMinT });
      texts[1].textContent = `${F.max} ${num.format(hi)} m`;
      texts[2].textContent = `${F.min} ${num.format(lo)} m`;
    };
    box.redraw();
    return box;
  }


  /**
   * The same cross-section for a window in a roof: the glass along the slope,
   * the cover come down from its top just enough for a sun 40° high in front
   * to light the room up to the distance, measured at the level of the glass's
   * lower edge, as shade.py does.
   */
  _figGeometrySloped(draft, baseline, tilt) {
    const F = T.fig;
    const box = el("div", "fig");
    box.style.color = "var(--secondary-text-color)";
    box.append(el("span", "cap", F.section));
    const NS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 170 152");
    svg.setAttribute("aria-hidden", "true");
    box.append(svg);
    // Words go in as text, never as markup.
    const mk = (tag, attrs, text) => {
      const n = document.createElementNS(NS, tag);
      for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, typeof v === "number" ? String(Math.round(v * 10) / 10) : v);
      if (text != null) n.textContent = text;
      svg.append(n);
      return n;
    };
    const num = new Intl.NumberFormat(LANG, { maximumFractionDigits: 2 });
    const cur = (k) => Number(Object.prototype.hasOwnProperty.call(draft, k) ? draft[k] : baseline[k]);
    const A = toRad(40), B = toRad(tilt);
    const cosI = Math.sin(A) * Math.cos(B) + Math.cos(A) * Math.sin(B);
    const dir = [Math.cos(B), -Math.sin(B)];  // along the glass, up towards the room
    const u = [Math.cos(A), Math.sin(A)];      // the ray, going down into the room
    // The drawing's room: "outside" takes the top-left corner, "room" the bottom-right.
    const X0 = 4, X1 = 166, Y0 = 16, Y1 = 140;

    box.redraw = () => {
      svg.replaceChildren();
      const d = Math.max(0, cur("shade_distance"));
      const hi = Math.max(0, cur("shade_max_height"));
      const lo = Math.min(Math.max(0, cur("shade_min_height")), hi);
      // Open length along the glass, held between closed and open like the real computation.
      const open = Math.min(hi, Math.max(lo, (d * Math.sin(A)) / cosI));
      const dLabel = `${F.distance} ${num.format(d)} m`, lLabel = `${F.length} ${num.format(hi)} m`;
      const width = (str) => str.length * 4.1;
      // Everything laid out around the glass's lower edge, where the patch is
      // measured, at k pixels per metre; the sun and the words keep their size.
      const layout = (k) => {
        const at = (m) => [dir[0] * m * k, dir[1] * m * k];
        const E = at(open), top = at(hi), bottom = at(lo);
        const r0 = [-dir[0] * 26, -dir[1] * 26], r1 = [top[0] + dir[0] * 22, top[1] + dir[1] * 22];
        const land = [E[0] - (u[0] * E[1]) / u[1], 0];
        const sun = [E[0] - u[0] * 46, E[1] - u[1] * 46];
        const end = d * k, mid = end / 2;
        // The length sits above the glass's top, over the outside, ending there.
        const lab = [top[0] - 4, top[1] - 8];
        const xs = [r0[0] - 4, r1[0] + 4, sun[0] - 8, end, land[0], mid - width(dLabel) / 2, mid + width(dLabel) / 2, lab[0] - width(lLabel)];
        const ys = [r0[1] + 4, r1[1] - 4, sun[1] - 8, 26, lab[1] - 8];
        return { E, top, bottom, r0, r1, land, sun, end, lab, x0: Math.min(...xs), x1: Math.max(...xs), y0: Math.min(...ys), y1: Math.max(...ys) };
      };
      let k = Math.min(110, 100 / Math.max(hi * Math.sin(B), 0.1), 130 / Math.max(hi * Math.cos(B) + d, 0.3));
      let L = layout(k);
      for (let i = 0; i < 30 && (L.x1 - L.x0 > X1 - X0 || L.y1 - L.y0 > Y1 - Y0); i++) L = layout(k *= 0.92);
      // Centred in the room left by the two corner words.
      const tx = (X0 + X1 - L.x0 - L.x1) / 2, ty = (Y0 + Y1 - L.y0 - L.y1) / 2;
      const g = mk("g", { transform: `translate(${tx.toFixed(1)} ${ty.toFixed(1)})` });
      const add = (tag, attrs, text) => g.append(mk(tag, attrs, text));
      const { E, top, bottom, r0, r1, land, sun, end, lab } = L;
      add("line", { x1: r0[0], y1: r0[1], x2: r1[0], y2: r1[1], stroke: "currentColor", "stroke-opacity": ".25", "stroke-width": 8 });
      add("line", { x1: bottom[0], y1: bottom[1], x2: top[0], y2: top[1], stroke: "var(--card-background-color)", "stroke-width": 4 });
      if (open < hi) add("line", { x1: E[0], y1: E[1], x2: top[0], y2: top[1], stroke: "var(--primary-color)", "stroke-width": 5, opacity: ".85" });
      add("line", { x1: 0, y1: 0, x2: 168 - tx, y2: 0, stroke: "currentColor", "stroke-opacity": ".45", "stroke-dasharray": "3 3" });
      // The ray, in from the sun through the cover's edge, down to that level.
      add("line", { x1: sun[0], y1: sun[1], x2: E[0], y2: E[1], stroke: "var(--ce-b-shade)", "stroke-width": 1.5 });
      add("line", { x1: E[0], y1: E[1], x2: land[0], y2: land[1], stroke: "var(--ce-b-shade)", "stroke-width": 1.5, "stroke-dasharray": "4 2" });
      add("circle", { cx: sun[0], cy: sun[1], r: 7, fill: "var(--ce-b-shade)" });
      for (const x of [0, end]) add("line", { x1: x, y1: 5, x2: x, y2: 13, stroke: "var(--fp-warn)", "stroke-width": 1.5 });
      add("line", { x1: 0, y1: 9, x2: end, y2: 9, stroke: "var(--fp-warn)", "stroke-width": 1.5 });
      add("text", { x: end / 2, y: 23, fill: "var(--fp-warn)", "text-anchor": "middle" }, dLabel);
      // The slope, and the glass's length along it.
      const r = 15;
      add("path", { d: `M${r} 0 A${r} ${r} 0 0 0 ${(dir[0] * r).toFixed(1)} ${(dir[1] * r).toFixed(1)}`,
        fill: "none", stroke: "currentColor", "stroke-opacity": ".6" });
      add("text", { x: r + 3, y: -2, fill: "currentColor" }, `${tilt}°`);
      add("text", { x: lab[0], y: lab[1], fill: "currentColor", "text-anchor": "end" }, lLabel);
      mk("text", { x: 4, y: 10, fill: "currentColor", "fill-opacity": ".6" }, F.outside);
      mk("text", { x: 166, y: 148, fill: "currentColor", "fill-opacity": ".6", "text-anchor": "end" }, F.room);
    };
    box.redraw();
    return box;
  }

  /**
   * Where the sun must be for this cover, in two views. Seen from above, with
   * the window at the bottom looking out: the sector of the two angles, the one
   * solar gain, the "sun facing" sensor and shading all use, starting at the
   * window's edges. Behind a wall nothing gets through; behind a roof, a sun
   * higher than the slope does; a flat window sees the whole sky. In profile:
   * the heights shading works between, one cone from the bottom edge (lowest)
   * to the top edge (highest), over the zenith on a roof. The sun is drawn
   * where it is now (sun.sun), relative to the cover's facade, when the cover
   * has one and the sun is up; faded when it does not reach the glass.
   */
  _figDetection(draft, baseline, geo) {
    const F = T.fig;
    const cur = (k) => Number(Object.prototype.hasOwnProperty.call(draft, k) ? draft[k] : baseline[k]);
    const f1 = (n) => n.toFixed(1);
    const { kind, tilt } = geo;
    const box = el("div", "fig2");
    const view = (caption, viewBox) => {
      const v = el("div", "figv");
      v.append(el("span", "cap", caption));
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("viewBox", viewBox);
      svg.setAttribute("aria-hidden", "true");
      v.append(svg);
      box.append(v);
      return svg;
    };
    // The top view is drawn 220 wide and shown 225, to match its column.
    const topSvg = view(F.top, "-2.5 0 225 150");
    const sideSvg = view(F.side, "0 0 150 150");
    const legend = el("div", "flegend");
    legend.append(
      el("span", "lg-sun", F.sectorSun),
      el("span", "lg-shade", F.sectorShade));
    const sunNow = el("span", "lg-dot", F.sunNow);
    legend.append(sunNow);
    box.append(legend);

    // The sun right now, seen from this cover's window; a template has no
    // facade, so no sun and no north.
    const facade = this._cfg.facades.find((f) => f.name === draft.facade);
    const az = facade ? facadeAzimuth(facade) : null;
    const now = facade ? sunFromFacade(this._hass, az) : null;
    sunNow.hidden = !now;

    // Top view: window from wl to wr at y = cy; each limit leaves its own edge
    // and stops on the circle of radius R around the window's centre. Only a
    // roof whose sector goes past its sides needs room below the window: it
    // then sits higher, on a smaller circle, so the sky behind fits too.
    const cx = 110, wl = 92, wr = 128;
    let cy = 118, R = 92;
    const reach = (x, deg, r) => rayToCircle(x, cy, cx, cy, deg, r);
    const sector = (a1, a2, r) => {
      const [x1, y1] = reach(wl, a1, r), [x2, y2] = reach(wr, a2, r);
      return `M${wl} ${cy} L${f1(x1)} ${f1(y1)} A${r} ${r} 0 ${a2 - a1 > 180 ? 1 : 0} 1 ${f1(x2)} ${f1(y2)} L${wr} ${cy} Z`;
    };
    const text = (x, y, s, color, anchor = "middle") =>
      `<text x="${f1(x)}" y="${f1(y)}" fill="${color}" text-anchor="${anchor}">${s}</text>`;
    const dot = (x, y, on) =>
      `<circle cx="${f1(x)}" cy="${f1(y)}" r="7" fill="var(--ce-b-shade)" ${on ? "" : 'fill-opacity=".45"'} stroke="var(--card-background-color)" stroke-width="2"/>`;
    const SHADE = 'fill="var(--ce-b-shade)" fill-opacity=".22" stroke="var(--ce-b-shade)" stroke-dasharray="3 3"';
    const CONE = 'fill="none" stroke="var(--primary-color)" stroke-width="1.6" stroke-dasharray="5 3"';
    // Profile of a wall: the window on the left, looking right; heights above
    // the horizon. The window spans wt..wb above the horizon at y = py; like
    // the top view, the lowest height leaves the bottom edge, the highest the top edge.
    const px = 18, py = 132, pr = 98, wt = py - 40, wb = py - 8, wc = (wt + wb) / 2;
    const pp = (height, r) => polar(px, wc, 90 - height, r);
    const fromEdge = (y, height, r) => rayToCircle(px, y, px, wc, 90 - height, r);

    const topView = (left, right, lit) => {
      // How far the sector reaches below the window, at most R; the caption
      // under the window needs 24. The whole is centred in the height.
      const below = kind === "roof" ? Math.sin(toRad(Math.min(90, Math.max(0, Math.max(left, right) - 90)))) : 0;
      R = Math.min(92, 130 / (1 + below));
      cy = (150 + R - Math.max(R * below, 24)) / 2;
      let s = "";
      if (kind === "flat") {
        // No front, no back: the sector, if the angles cut one, leaves the window's centre.
        const c = [110, 72], r = 64;
        s += left + right >= 360
          ? `<circle cx="${c[0]}" cy="${c[1]}" r="${r}" ${SHADE}/>`
          : (() => {
            const [ax, ay] = polar(c[0], c[1], -left, r), [bx, by] = polar(c[0], c[1], right, r);
            return `<path d="M${c[0]} ${c[1]} L${f1(ax)} ${f1(ay)} A${r} ${r} 0 ${left + right > 180 ? 1 : 0} 1 ${f1(bx)} ${f1(by)} Z" ${SHADE}/>`;
          })();
        s += `<rect x="${c[0] - 9}" y="${c[1] - 9}" width="18" height="18" rx="2" fill="var(--primary-color)"/>`;
        s += text(110, 146, F.wholeSky, "var(--secondary-text-color)");
        if (now) {
          const [sx, sy] = polar(c[0], c[1], now.off, 12 + (r - 12) * Math.cos(toRad(now.el)));
          s += `<line x1="${c[0]}" y1="${c[1]}" x2="${f1(sx)}" y2="${f1(sy)}" stroke="var(--ce-b-shade)" stroke-dasharray="2 3"/>` + dot(sx, sy, lit);
        }
        return s;
      }
      // Unmasked on both sides, the sector is the whole circle.
      s += left >= 180 && right >= 180
        ? `<circle cx="${cx}" cy="${cy}" r="${R}" ${SHADE}/>`
        : `<path d="${sector(-left, right, R)}" ${SHADE}/>`;
      // Behind a wall nothing; behind a roof, only a sun above it.
      s += `<rect x="-2.5" y="${cy}" width="225" height="${150 - cy}" fill="var(--card-background-color)" fill-opacity="${kind === "wall" ? ".55" : ".3"}"/>`;
      s += text(cx, Math.min(146, cy + 20), kind === "wall" ? F.room : F.behindRoof, "var(--secondary-text-color)");
      s += `<line x1="8" y1="${cy}" x2="212" y2="${cy}" stroke="var(--secondary-text-color)" stroke-width="1.6"/>`;
      s += `<rect x="${wl}" y="${cy - 2.5}" width="${wr - wl}" height="5" fill="var(--primary-color)"/>`;
      for (const [edge, deg, v, side] of [[wl, -left, left, -1], [wr, right, right, 1]]) {
        if (kind !== "wall" && v >= 180) continue;  // no mask on that side: nothing to label
        let [x, y] = reach(edge, deg, R + 8);
        y = v <= 90 ? Math.min(cy - 4, y) : Math.min(146, Math.max(10, y));
        x = side < 0 ? Math.max(2, x) : Math.min(218, x);
        const anchor = x < cx - 4 ? "start" : x > cx + 4 ? "end" : "middle";
        s += text(x, y, `${v}°`, "var(--ce-b-shade)", anchor);
      }
      if (now) {
        const r = 22 + (R - 22) * Math.cos(toRad(now.el));
        const [sx, sy] = polar(cx, cy, now.off, r);
        s += `<line x1="${cx}" y1="${cy}" x2="${f1(sx)}" y2="${f1(sy)}" stroke="var(--ce-b-shade)" stroke-dasharray="2 3"/>` + dot(sx, sy, lit);
      }
      return s;
    };

    const sideWall = (emin, emax) => {
      let p = `<line x1="${px}" y1="${py}" x2="146" y2="${py}" stroke="var(--secondary-text-color)" stroke-width="1.6"/>`;
      p += text(144, py + 13, F.horizon, "var(--secondary-text-color)", "end");
      p += `<rect x="${px - 6}" y="${py - 52}" width="6" height="52" fill="var(--secondary-text-color)" fill-opacity=".35"/>`;
      p += `<rect x="${px - 6}" y="${py - 40}" width="6" height="32" fill="var(--primary-color)"/>`;
      const [ax, ay] = fromEdge(wb, emin, pr - 6), [bx, by] = fromEdge(wt, emax, pr - 6);
      p += `<path d="M${px} ${wb} L${f1(ax)} ${f1(ay)} A${pr - 6} ${pr - 6} 0 0 0 ${f1(bx)} ${f1(by)} L${px} ${wt} Z" ${CONE}/>`;
      const [t1x, t1y] = fromEdge(wb, emin, pr + 8);
      p += text(Math.min(146, t1x), Math.min(py - 3, t1y), `${emin}°`, "var(--primary-color)", "end");
      const [t2x, t2y] = fromEdge(wt, emax, pr - 18);
      p += text(t2x + 10, Math.max(10, t2y), `${emax}°`, "var(--primary-color)", "start");
      if (now) {
        const [sx, sy] = pp(Math.min(89, now.el), pr - 28);
        p += `<line x1="${px}" y1="${wc}" x2="${f1(sx)}" y2="${f1(sy)}" stroke="var(--ce-b-shade)" stroke-dasharray="2 3"/>`;
        p += `<circle cx="${f1(sx)}" cy="${f1(sy)}" r="7" fill="var(--ce-b-shade)" stroke="var(--card-background-color)" stroke-width="2"/>`;
        p += text(sx + 10, sy + 4, `${Math.round(now.el)}°`, "var(--primary-text-color)", "start");
      }
      return p;
    };

    // Profile of a roof or a flat window: the glass on its slope, looking up
    // and to the right; the room below it. One cone, the lowest height from
    // the bottom edge, the highest from the top edge, read over the zenith.
    const sideSloped = (emin, emax, lim, lit) => {
      const up = [-Math.cos(toRad(tilt)), -Math.sin(toRad(tilt))], G = 30;
      const [Gc, r] = profileFit(kind === "roof" ? [[emin, emax]]
        : emax >= 90 ? [[emin, 180 - emin]] : [[emin, emax], [180 - emax, 180 - emin]], up, G, kind === "roof");
      const Pb = [Gc[0] - (up[0] * G) / 2, Gc[1] - (up[1] * G) / 2];
      const Pt = [Gc[0] + (up[0] * G) / 2, Gc[1] + (up[1] * G) / 2];
      const ray = (from, h, rr = r) => rayToCircle(from[0], from[1], Gc[0], Gc[1], 90 - h, rr);
      const pt = (q) => `${f1(q[0])} ${f1(q[1])}`;
      const far = (t) => [Pb[0] + up[0] * t, Pb[1] + up[1] * t];
      const A0 = far(-300), A1 = far(300);
      let p = `<polygon points="${pt(A0)} ${pt(A1)} ${f1(A1[0] - 300)} ${f1(A1[1])} ${f1(A1[0] - 300)} 400 ${f1(A0[0] + 300)} 400" fill="var(--card-background-color)" fill-opacity=".55"/>`;
      p += `<line x1="${Pb[0]}" y1="${Pb[1]}" x2="146" y2="${Pb[1]}" stroke="var(--secondary-text-color)" stroke-dasharray="3 3"/>`;
      p += text(144, Pb[1] + 13, F.horizon, "var(--secondary-text-color)", "end");
      const cone = (a, ha, b, hb) =>
        `<path d="M${pt(a)} L${pt(ray(a, ha))} A${r} ${r} 0 0 0 ${pt(ray(b, hb))} L${pt(b)} Z" ${CONE}/>`;
      if (kind === "roof") p += cone(Pb, emin, Pt, emax);
      else if (emax >= 90) p += cone(Pb, emin, Pt, 180 - emin);
      else p += cone(Pb, emin, Pt, emax) + cone(Pb, 180 - emax, Pt, 180 - emin);
      p += `<line x1="${f1(A0[0])}" y1="${f1(A0[1])}" x2="${f1(A1[0])}" y2="${f1(A1[1])}" stroke="var(--secondary-text-color)" stroke-opacity=".6" stroke-width="5"/>`;
      p += `<line x1="${f1(Pb[0])}" y1="${f1(Pb[1])}" x2="${f1(Pt[0])}" y2="${f1(Pt[1])}" stroke="var(--primary-color)" stroke-width="5"/>`;
      if (kind === "roof") {
        const a = 16;
        p += `<line x1="${f1(Pt[0])}" y1="${f1(Pt[1])}" x2="${f1(Pt[0] - 30)}" y2="${f1(Pt[1])}" stroke="var(--secondary-text-color)" stroke-dasharray="2 3"/>`;
        p += `<path d="M${f1(Pt[0] - a)} ${f1(Pt[1])} A${a} ${a} 0 0 1 ${f1(Pt[0] + up[0] * a)} ${f1(Pt[1] + up[1] * a)}" fill="none" stroke="var(--secondary-text-color)"/>`;
        p += text(Pt[0] - a - 3, Pt[1] + 10, `${tilt}°`, "var(--primary-text-color)", "end");
      }
      const [t1x, t1y] = ray(Pb, emin, r + 8);
      p += text(Math.min(146, t1x), Math.min(Pb[1] - 3, t1y), `${emin}°`, "var(--primary-color)", "end");
      if (kind === "roof" && emax < lim) {
        const [t2x, t2y] = ray(Pt, emax, r - 14);
        const label = emax <= 90 ? `${emax}°` : `${180 - emax}° ${F.behind}`;
        p += text(t2x + (emax <= 90 ? 8 : -8), Math.max(10, t2y), label, "var(--primary-color)", emax <= 90 ? "start" : "end");
      }
      if (now) {
        const back = kind === "roof" && Math.abs(now.off) > 90;
        const [sx, sy] = polar(Gc[0], Gc[1], back ? now.el - 90 : 90 - now.el, r - 22);
        p += `<line x1="${f1(Gc[0])}" y1="${f1(Gc[1])}" x2="${f1(sx)}" y2="${f1(sy)}" stroke="var(--ce-b-shade)" stroke-dasharray="2 3"/>` + dot(sx, sy, lit);
        p += text(sx + (back ? -10 : 10), sy + 4, `${Math.round(now.el)}°`, "var(--primary-text-color)", back ? "end" : "start");
      }
      return p;
    };

    box.redraw = () => {
      const cap = kind === "wall" ? 90 : 180;
      const left = Math.min(cur("angle_left"), cap), right = Math.min(cur("angle_right"), cap);
      const lim = kind === "wall" ? 90 : heightLimit(tilt);
      const emin = Math.min(cur("shade_min_elevation"), lim), emax = Math.min(cur("shade_max_elevation"), lim);
      const lit = !!now && now.off >= -left && now.off <= right && sunOnGlass(now.off, now.el, tilt);
      let s = topView(left, right, lit);
      // Where north is from this window, like the arrow of the facade list.
      if (az !== null) {
        s += `<g transform="rotate(${f1(-az)} 14 14)"><circle cx="14" cy="14" r="10" fill="var(--secondary-background-color)" stroke="var(--divider-color)"/>`
          + `<path d="M14 6 L18 14 L14 12 L10 14 Z" fill="var(--fp-bad)"/></g>`;
        s += text(14, 33, T.dirs[0], "var(--fp-bad)");
      }
      topSvg.innerHTML = s;
      sideSvg.innerHTML = kind === "wall" ? sideWall(emin, emax) : sideSloped(emin, emax, lim, lit);
    };
    box.redraw();
    return box;
  }

  /**
   * The behavior sections as cards, two columns: the window and its shading on
   * the left, the sun and solar gain on the right. A section's activation flag
   * becomes the switch in its header, and dims the numbers it governs. Under a
   * template each card counts what it inherits and what the cover overrides,
   * and `onCount(own)` hears the cover's total after every change.
   */
  _behaviorGrid(sections, draft, baseline, tplName, onCount) {
    const raw = this._cfg.behavior?.fields || {};
    const geo = this._slope(draft);
    // The angles and heights stop where this window's shape stops them.
    const capped = (name, max) => raw[name] && { ...raw[name], max: Math.min(raw[name].max, max) };
    const specs = {
      ...raw,
      angle_left: capped("angle_left", geo.angleMax),
      angle_right: capped("angle_right", geo.angleMax),
      shade_min_elevation: capped("shade_min_elevation", geo.heightMax),
      shade_max_elevation: capped("shade_max_elevation", geo.heightMax),
    };
    // A flat window has no patch to hold near a wall: one position in the sun
    // replaces the geometry. Every other window has no use for that position.
    const flatOnly = ["shade_sun_position"];
    const notFlat = ["shade_distance", "shade_max_height", "shade_min_height", "shade_minimum_position"];
    const hidden = new Set(geo.kind === "flat" ? notFlat : flatOnly);
    const roof = geo.kind === "roof";
    const has = (k) => Object.prototype.hasOwnProperty.call(draft, k);
    const cols = el("div", "ed-cols");
    const left = el("div", "ed-stack");
    const right = el("div", "ed-stack");
    cols.append(left, right);
    const side = { geometry: left, shading: left, detection: right, solar_gain: right };
    const cards = [];

    // Counted off the rows themselves, so the numbers can never disagree with
    // what the rows show. A card only speaks of its overrides, when it has any:
    // following the template is the rule and needs no counting.
    const recount = () => {
      let total = 0;
      const per = {};
      for (const { card, cnt, key } of cards) {
        const own = card.querySelectorAll(".numf.ovr").length;
        total += own;
        per[key] = own;
        card.classList.toggle("no-own", !own);
        if (cnt) cnt.textContent = own ? T.overrides(own) : "";
      }
      onCount?.(total, per);
    };

    for (const { key, fields } of sections) {
      const card = this._edCard(SECTION_ICONS[key] || "mdi:tune",
        T.sectionTitles[key] || T.sections[key] || key, T.sectionSubs[key]);
      card.classList.add("sect");
      card.dataset.key = key;
      const h3 = card.querySelector("h3");
      const cnt = tplName ? el("span", "cnt") : null;
      if (cnt) h3.append(cnt);

      // Activation flags are cover-specific: no template value to fall back to.
      const flag = fields.find((f) => specs[f]?.type === "boolean");
      if (flag) {
        const on = !!(has(flag) ? draft[flag] : baseline[flag]);
        card.classList.toggle("dim", !on);
        const sw = this._switch(on, (v) => { draft[flag] = v; card.classList.toggle("dim", !v); }, T.fields[flag]);
        sw.classList.add("end");
        if (cnt) sw.style.marginLeft = "var(--fp-s2)";
        h3.append(sw);
      }

      const fig = key === "geometry" ? (geo.kind === "flat" ? null : this._figGeometry(draft, baseline, geo))
        : key === "detection" ? this._figDetection(draft, baseline, geo) : null;
      const changed = () => { fig?.redraw(); recount(); };
      const beside = key === "geometry" ? null : ["angle_left", "angle_right"];
      const nums = fields.filter((f) => specs[f] && specs[f].type !== "boolean" && !hidden.has(f));
      // Pairs shown as one double slider: the second of each is drawn with the first.
      const pair = (a, b) => nums.includes(a) && nums.includes(b);
      const merge = pair("shade_min_elevation", "shade_max_elevation");
      const mergeAngles = pair("angle_left", "angle_right");
      const skip = (f) => (merge && f === "shade_max_elevation") || (mergeAngles && f === "angle_right");
      const mkRow = (f) => (merge && f === "shade_min_elevation"
        ? this._elevationRow("shade_min_elevation", "shade_max_elevation", specs, draft, baseline, tplName, changed)
        : mergeAngles && f === "angle_left"
          ? this._sectorRow("angle_left", "angle_right", specs, draft, baseline, tplName, changed)
          : this._behaviorRow(f, specs[f], draft, baseline, tplName, changed,
            roof ? T.fieldHintsRoof?.[f] : undefined, roof ? T.fieldsRoof?.[f] : undefined));
      if (key === "detection") {
        // Two groups, each marked like its shape on the picture above: the
        // sector of the two angles, which solar gain, the "sun facing" sensor
        // and shading all use, then the heights only shading looks at.
        const body = el("div", "sect-body");
        body.append(fig);
        const group = (cls, title, names) => {
          const g = el("div", `sgroup ${cls}`);
          g.append(el("h4", "", title));
          for (const f of names) {
            if (skip(f)) continue;
            g.append(mkRow(f));
          }
          if (g.childElementCount > 1) body.append(g);
        };
        const sunSide = ["angle_left", "angle_right"];
        group("g-sun", T.detGroupSun, nums.filter((f) => sunSide.includes(f)));
        group("g-shade", T.detGroupShade, nums.filter((f) => !sunSide.includes(f)));
        card.append(body);
        cards.push({ card, cnt, key });
        (side[key] || right).append(card);
        continue;
      }
      const body = el("div", "sect-body");
      const next = fig ? el("div") : body;
      const after = el("div");
      for (const f of nums) {
        if (skip(f)) continue;
        const row = mkRow(f);
        (fig && beside && !beside.includes(f) ? after : next).append(row);
      }
      if (fig) {
        const wf = el("div", "withfig");
        wf.append(fig, next);
        body.append(wf);
        if (after.childElementCount) {
          after.firstChild.classList.add("sep-top");
          body.append(after);
        }
      }
      card.append(body);
      cards.push({ card, cnt, key });
      (side[key] || (left.childElementCount <= right.childElementCount ? left : right)).append(card);
    }
    recount();
    return cols;
  }

  /* ---------- MODES (editable) ---------- */

  _renderModes(wrap) {
    const usage = this._usage();

    if (this._edit?.section === "mode") {
      this._modeEditor(wrap, usage);
      return;
    }

    const bar = el("div", "toolbar");
    const add = el("button", "btn primary");
    add.append(icon("mdi:plus"), document.createTextNode(T.addMode));
    add.addEventListener("click", () => {
      this._openEditor({
        section: "mode", idx: -1,
        draft: { name: "", icon: "mdi:help-circle", color: "#FFFFFF",
                 lock: false, behavior: null, hidden: false, priority: false,
                 duration: null, return_mode: null, spares: [], fallback: null },
      });
      this._render();
    });
    bar.classList.add("list-head");
    bar.append(el("h2", "", T.modesCount(this._cfg.modes.length)), el("span", "hint", T.dragHint),
      el("span", "spacer"), add);
    wrap.append(bar);

    // A list, not a grid: the order is the selector's, and a list shows an
    // order without numbers; dragging up or down is the gesture it asks for.
    const list = el("div", "card mlist");

    this._cfg.modes.forEach((m, i) => {
      const row = el("div", "mrow");
      row.tabIndex = 0;
      row.draggable = true;
      const open = () => {
        this._openEditor({ section: "mode", idx: i, draft: { ...m } });
        this._render();
      };
      row.addEventListener("click", open);
      row.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
      });
      row.addEventListener("dragstart", (e) => {
        this._dragFrom = i;
        e.dataTransfer.effectAllowed = "move";
        row.classList.add("dragging");
      });
      row.addEventListener("dragend", () => row.classList.remove("dragging"));
      row.addEventListener("dragover", (e) => { e.preventDefault(); row.classList.add("drop"); });
      row.addEventListener("dragleave", () => row.classList.remove("drop"));
      row.addEventListener("drop", (e) => {
        e.preventDefault();
        row.classList.remove("drop");
        this._reorderModes(this._dragFrom, i);
      });

      const mico = el("span", "mico");
      mico.style.background = `color-mix(in srgb, ${m.color || "#888888"} 16%, transparent)`;
      mico.style.color = m.color || "var(--secondary-text-color)";
      mico.append(icon(m.icon || "mdi:help-circle"));
      // How it places the covers, in words under its name; the chips keep to
      // what changes its behaviour.
      const names = el("span", "mnames");
      names.append(el("span", "nm", m.name),
        el("span", "meta", `${T.behaviorKind[m.behavior || "none"]} · ${T.covers(usage[m.name] || 0)}`));

      const chips = el("div", "chips");
      const chip = (cls, ico, text, title) => {
        const c = el("span", `chip ${cls}`.trim());
        c.append(icon(ico), document.createTextNode(text));
        if (title) c.title = title;
        chips.append(c);
      };
      if (m.lock) chip("lock", "mdi:lock-outline", T.lock);
      if (m.duration) chip("timer", "mdi:timer-outline", T.timedChip(m.duration, m.return_mode));
      if (m.priority) chip("prio", "mdi:alert-decagram-outline", T.priority);
      if (m.spares?.length) chip("", "mdi:shield-outline", T.sparesChip(m.spares), m.spares.join(", "));
      if (m.fallback) chip("", "mdi:arrow-u-left-top", T.fallbackChip(m.fallback));
      if (m.hidden) chip("", "mdi:eye-off-outline", T.hidden);

      row.append(icon("mdi:drag-vertical", "grip"), mico, names, chips, icon("mdi:chevron-right", "chev"));
      list.append(row);
    });

    wrap.append(list);
  }

  /** Drag reorder. The stored order drives the order of the select.*_cx_mode options. */
  _reorderModes(from, to) {
    if (from === to || from == null) return;
    const items = this._cfg.modes.map((m) => ({ ...m }));
    const [moved] = items.splice(from, 1);
    items.splice(to, 0, moved);
    this._saveSection("mode", items);
  }

  _modeEditor(wrap, usage) {
    const { idx, draft } = this._edit;
    const creating = idx < 0;
    const rerender = () => { this._render(); };
    // One column, in the order of the questions: what it is called, how it
    // places the covers, what happens meanwhile, how it behaves when sent to
    // the whole house, then the rest.
    const page = el("div", "form-col");
    wrap.append(page);
    wrap = page;

    wrap.append(this._backBar(T.backToModes));

    /* identity: the plate and the selector chip are live previews */
    const idCard = el("section", "card");
    const grid = el("div", "ed-ident");
    const plate = el("div", "ed-plate");
    const plateIcon = icon(draft.icon || "mdi:help-circle");
    plate.append(plateIcon);
    const pill = el("span", "mpill");
    const pillIcon = icon(draft.icon || "mdi:help-circle");
    const pillName = el("span");
    pill.append(pillIcon, pillName);
    const paint = () => {
      const c = draft.color || "#888888";
      plate.style.color = c;
      plate.style.background = `color-mix(in srgb, ${c} 16%, transparent)`;
      plate.style.borderColor = `color-mix(in srgb, ${c} 40%, transparent)`;
      // The label keeps the text colour: a mode set to #FFFFFF would make its
      // own name vanish on a light theme. The tint and the icon carry the hue.
      pill.style.background = `color-mix(in srgb, ${c} 16%, transparent)`;
      pillIcon.style.color = c;
      plateIcon.setAttribute("icon", draft.icon || "mdi:help-circle");
      pillIcon.setAttribute("icon", draft.icon || "mdi:help-circle");
      pillName.textContent = draft.name || T.newMode;
    };

    // The colour wheel and its hex code, kept in step both ways.
    const color = el("div", "colorpick");
    const wheel = document.createElement("input");
    wheel.type = "color";
    wheel.value = (draft.color || "#FFFFFF").toLowerCase();
    wheel.title = T.colorPick;
    wheel.setAttribute("aria-label", T.colorPick);
    const hex = this._edInput((draft.color || "#FFFFFF").toUpperCase(), (v) => {
      const want = (v.trim().startsWith("#") ? v.trim() : `#${v.trim()}`).toUpperCase();
      const ok = /^#[0-9A-F]{6}$/.test(want);
      hex.setAttribute("aria-invalid", String(!ok));
      if (!ok) return;
      draft.color = want;
      wheel.value = want.toLowerCase();
      paint();
    });
    hex.maxLength = 7;
    hex.spellcheck = false;
    hex.setAttribute("aria-label", T.colorHex);
    wheel.addEventListener("input", () => {
      draft.color = wheel.value.toUpperCase();
      hex.value = draft.color;
      hex.setAttribute("aria-invalid", "false");
      paint();
    });
    hex.addEventListener("change", () => { hex.value = (draft.color || "#FFFFFF").toUpperCase(); hex.setAttribute("aria-invalid", "false"); });
    color.append(wheel, hex);

    const preview = el("div", "ed-preview");
    preview.append(el("span", "", T.inSelector), pill);
    grid.append(plate,
      this._labeled(T.name, this._edInput(draft.name, (v) => { draft.name = v; paint(); }, "big"), "wide"),
      this._labeled(T.icon, this._haSelector({ icon: {} }, draft.icon, (v) => {
        draft.icon = v || "mdi:help-circle";
        paint();
      })),
      this._labeled(T.color, color),
      preview);
    idCard.append(grid);
    wrap.append(idCard);
    paint();

    const cols = el("div", "ed-stack");
    cols.style.marginTop = "var(--fp-s4)";
    const left = cols;
    const right = cols;

    /* how this mode places the covers */
    const beh = this._edCard("mdi:tune-variant", T.behaviorTitle, T.behaviorCardSub);
    const seg = el("div", "bseg");
    seg.setAttribute("role", "group");
    seg.setAttribute("aria-label", T.behaviorTitle);
    const segBtns = [];
    for (const key of ["none", "auto_shade", "solar_gain"]) {
      const value = key === "none" ? null : key;
      const b = el("button");
      b.type = "button";
      b.style.setProperty("--bc", BEHAVIORS[key].color);
      const [title, sub] = T.behaviorOpts[key];
      b.append(icon(BEHAVIORS[key].icon), el("span", "", title), el("small", "", sub));
      b.setAttribute("aria-pressed", String((draft.behavior ?? null) === value));
      b.addEventListener("click", () => {
        draft.behavior = value;
        for (const [other, v] of segBtns) other.setAttribute("aria-pressed", String(v === value));
      });
      segBtns.push([b, value]);
      seg.append(b);
    }
    beh.append(seg, this._note(T.behaviorHint));
    left.append(beh);

    /* while the mode is on */
    const during = this._edCard("mdi:play-circle-outline", T.whileTitle, T.whileSub);
    during.append(this._optRow("mdi:lock-outline", T.lockField, T.lockHint, draft.lock,
      (v) => { draft.lock = v; }));
    // A mode other modes return to cannot take a duration (the server refuses
    // it too): say so before the user tries, rather than after the save.
    const returners = creating ? [] : this._cfg.modes
      .filter((m) => m.duration && m.return_mode === this._cfg.modes[idx].name)
      .map((m) => m.name);
    during.append(this._optRow("mdi:timer-outline", T.durationField,
      returners.length ? T.usedAsReturn(returners) : T.durationHint, !!draft.duration, (v) => {
        draft.duration = v ? (draft.duration || 60) : null;
        if (!v) draft.return_mode = null;
        rerender();
      }));
    if (draft.duration) {
      const more = el("div", "opt-more");
      const mins = document.createElement("input");
      mins.type = "number";
      mins.min = "1";
      mins.max = "1440";
      mins.step = "1";
      mins.value = String(draft.duration);
      mins.setAttribute("aria-label", T.durationLabel);
      mins.addEventListener("input", () => {
        // An empty box is a transient state while typing, not a zero.
        if (mins.value !== "") draft.duration = Number(mins.value);
      });
      // Only modes without a duration: every countdown must end on a mode
      // that starts no other (the server refuses anything else too).
      const targets = this._cfg.modes.filter((m) => !m.duration && m.name !== draft.name);
      const ret = this._edSelect(draft.return_mode,
        [[null, T.returnBase], ...targets.map((m) => [m.name, m.name])],
        (v) => { draft.return_mode = v; });
      ret.className = "";
      ret.setAttribute("aria-label", T.returnField);
      more.append(el("span", "", T.timedFor), mins, el("span", "", T.timedThen), ret, this._info(T.returnHint));
      during.append(more);
    }
    left.append(during);

    /* grouped requests: which modes this one leaves alone, and its fallback,
       as two sentences to complete */
    const others = this._cfg.modes.filter((m) => m.name !== (creating ? draft.name : this._cfg.modes[idx].name));
    const grouped = this._edCard("mdi:home-group", T.groupedTitle, T.groupedHint);
    grouped.querySelector("h3").append(this._info(T.groupedInfo));
    draft.spares = [...(draft.spares || [])];
    const colorOf = (n) => this._cfg.modes.find((m) => m.name === n)?.color || "#888888";
    const sp = el("div", "sentence");
    const spLabel = el("span", "", T.sparesField);
    const chosen = el("span", "chipline");
    const add = document.createElement("select");
    add.className = "addsel";
    add.setAttribute("aria-label", `${T.sparesField} ${T.sparesAdd}`);
    const none = el("span", "ed-sub inline", T.sparesNone);
    const paintSpares = () => {
      chosen.replaceChildren();
      for (const n of draft.spares) {
        const b = el("button", "toggle");
        b.type = "button";
        b.setAttribute("aria-pressed", "true");
        b.title = `${T.removeEntity} ${n}`;
        const dot = el("span", "mdot");
        dot.style.background = colorOf(n);
        b.append(dot, document.createTextNode(n), icon("mdi:close", "x"));
        b.addEventListener("click", () => { draft.spares = draft.spares.filter((x) => x !== n); paintSpares(); });
        chosen.append(b);
      }
      add.replaceChildren();
      const head = document.createElement("option");
      head.value = "";
      head.textContent = T.sparesAdd;
      add.append(head);
      for (const m of others) {
        if (draft.spares.includes(m.name)) continue;
        const o = document.createElement("option");
        o.value = m.name;
        o.textContent = m.name;
        add.append(o);
      }
      add.hidden = add.options.length < 2;
      none.hidden = draft.spares.length > 0;
    };
    add.addEventListener("change", () => {
      if (add.value) draft.spares = [...draft.spares, add.value];
      paintSpares();
      this._syncSaveBar?.();
    });
    paintSpares();
    sp.append(spLabel, chosen, add, this._info(T.sparesHint));
    const fb = el("div", "sentence");
    const fallback = this._edSelect(draft.fallback ?? null,
      [[null, T.fallbackNone], ...others.map((m) => [m.name, m.name])],
      (v) => { draft.fallback = v; }, "inline");
    fallback.setAttribute("aria-label", T.fallbackField);
    fb.append(el("span", "", T.fallbackField), fallback);
    grouped.append(sp, none, fb, this._note(T.fallbackHint));
    right.append(grouped);

    /* rarely touched: open on its own only when something in it is on */
    const advCard = el("section", "card ed-card");
    const adv = document.createElement("details");
    adv.className = "adv";
    adv.open = this._advOpen ?? !!(draft.priority || draft.hidden);
    adv.addEventListener("toggle", () => { this._advOpen = adv.open; });
    const sum = document.createElement("summary");
    const badge = el("span", "badge");
    const resum = () => { badge.textContent = T.advSummary(!!draft.priority, !!draft.hidden); };
    resum();
    sum.append(icon("mdi:cog-outline"), el("h3", "", T.advanced), badge, icon("mdi:chevron-down", "chev-d"));
    const advBody = el("div", "adv-body");
    advBody.append(
      this._optRow("mdi:alert-decagram-outline", T.priorityField, T.priorityHint, draft.priority,
        (v) => { draft.priority = v; resum(); }),
      this._optRow("mdi:eye-off-outline", T.hiddenField, T.hiddenHint, draft.hidden,
        (v) => { draft.hidden = v; resum(); }));
    adv.append(sum, advBody);
    advCard.append(adv);
    right.append(advCard);
    wrap.append(cols);

    const used = usage[draft.name] || 0;
    wrap.append(this._saveBar(() => {
      const items = this._cfg.modes.map((m) => ({ ...m }));
      if (creating) items.push(draft); else items[idx] = draft;
      this._saveSection("mode", items);
    }, creating ? null : {
      used, reason: T.inUseTitle(used),
      onDelete: () => this._saveSection("mode", this._cfg.modes.filter((_, i) => i !== idx).map((m) => ({ ...m }))),
    }));
  }

  /* ---------- VOLETS (editable) ---------- */

  _renderCovers(wrap) {
    if (this._edit?.section === "cover") {
      this._coverEditor(wrap);
      return;
    }

    const bar = el("div", "toolbar");
    const add = el("button", "btn primary");
    add.append(icon("mdi:plus"), document.createTextNode(T.addCover));
    add.addEventListener("click", () => {
      this._openEditor({
        section: "cover", idx: -1,
        draft: { entity_id: "", facade: this._cfg.facades[0]?.name || null,
                 template: null, exclusion: [], inhibition: [], modes: {},
                 shade_enable: false, solar_gain_enable: false },
      });
      this._render();
    });
    bar.classList.add("list-head");
    bar.append(el("h2", "", T.covers(this._cfg.covers.length)), el("span", "spacer"), add);
    wrap.append(bar);

    // One grid per facade, under its name: the order of the matrix and the
    // schedules, so a cover sits among the same neighbours on every tab.
    const groups = el("div", "fgroups");
    wrap.append(groups);
    for (const [facade, covers] of this._grouped()) {
      if (!covers.length) continue;
      const fac = this._cfg.facades.find((f) => f.name === facade);
      const gh = el("div", "grp-h");
      gh.append(el("span", "", facade ? `${T.facade} ${facade}` : T.noFacade));
      if (fac) gh.append(el("span", "az", [`${facadeAzimuth(fac)}°`, T.slopeShort(facadeTilt(fac))].filter(Boolean).join(" · ")));
      const grid = el("div", "grid covers");
      // A facade of two covers asks for two card widths; the groups then flow
      // side by side and share the rows, instead of each taking a whole one.
      const group = el("section", "fgroup");
      group.style.setProperty("--n", String(covers.length));
      group.append(gh, grid);
      groups.append(group);
      for (const c of covers) {
        const idx = this._cfg.covers.indexOf(c);
        const card = el("div", "card clickable");
        card.tabIndex = 0;
        const open = () => {
          this._openEditor({ section: "cover", idx, draft: JSON.parse(JSON.stringify(c)) });
          this._render();
        };
        card.addEventListener("click", open);
        card.addEventListener("keydown", (e) => {
          if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
        });

        // Who it is, then what it does now, then what comes next. The facade
        // is the group's title; the entity id is on the name's tooltip.
        const head = el("div", "c-head");
        head.append(this._coverPic(c));
        const names = el("span");
        const nm = el("span", "nm", this._coverName(c));
        nm.title = c.entity_id;
        const meta = [c.template, T.modesCount(Object.keys(c.modes || {}).length)].filter(Boolean).join(" · ");
        names.append(nm, el("br"), el("span", "meta", meta));
        head.append(names);
        head.append(el("span", "spacer"), icon("mdi:chevron-right", "chev"));
        card.append(head);
        const status = this._statusLine(c);
        if (status) card.append(status);
        card.append(...this._schedLine(c));

        // Only what is on: a feature that is off says nothing.
        const feats = el("div", "feats");
        const feat = (cls, ico, text) => {
          const ch = el("span", `chip ${cls}`);
          ch.append(icon(ico), document.createTextNode(text));
          feats.append(ch);
        };
        if (c.shade_enable) feat("ok", "mdi:weather-sunny", T.shading);
        if (c.solar_gain_enable) feat("ok", "mdi:thermometer", T.solarGain);
        const overrides = this._overrideCount(c);
        if (overrides) feat("ovr", "mdi:pencil-outline", T.overrides(overrides));
        if (feats.childElementCount) card.append(feats);
        grid.append(card);
      }
    }
  }

  /** Every state the cover cards show, as one string: the redraw trigger. */
  _statusSignature() {
    const st = this._hass?.states || {};
    const day = st[this._cfg?.day_entity]?.attributes;
    const parts = [day?.opening, day?.closing, day?.next_change];
    for (const c of this._cfg?.covers || []) {
      const ids = this._cfg.helpers?.[c.entity_id] || {};
      const sel = st[ids.select];
      const cov = st[c.entity_id];
      parts.push(sel?.state, sel?.attributes?.mode_ends_at, st[ids.lock]?.state,
        cov?.attributes?.current_position, cov?.attributes?.memory,
        ...[...(c.exclusion || []), ...(c.inhibition || [])].map((e) => st[e]?.state));
    }
    return JSON.stringify(parts);
  }

  /** Why the cover is where it is: its mode, its position, then whatever holds
   *  it back (a countdown, the lock, an exclusion or an inhibition on). */
  _statusLine(c) {
    const st = this._hass.states;
    const ids = this._cfg.helpers?.[c.entity_id];
    const sel = ids && st[ids.select];
    if (!sel) return null;
    const line = el("div", "status");
    const mode = this._cfg.modes.find((m) => m.name === sel.state);
    // The mode's colour as on its tile and in the matrix: on the icon, the
    // tint and the edge. The name keeps the text colour, so a mode set to
    // #FFFFFF stays readable on a light theme.
    const tint = mode?.color || "#888888";
    const pill = el("span", "smode");
    pill.style.background = `color-mix(in srgb, ${tint} 18%, transparent)`;
    pill.style.border = `1px solid color-mix(in srgb, ${tint} 45%, transparent)`;
    const glyph = icon(mode?.icon || "mdi:help-circle");
    glyph.style.color = tint;
    pill.append(glyph, document.createTextNode(sel.state));
    line.append(pill);
    // The position drawn as in the matrix, and written.
    const pos = st[c.entity_id]?.attributes?.current_position;
    if (pos != null) {
      const gauge = el("span", "gauge big");
      const fill = el("i");
      fill.style.width = `${pos}%`;
      gauge.append(fill);
      line.append(gauge, el("span", "spos big", `${pos} %`));
    }
    const chip = (cls, ico, text, title) => {
      const ch = el("span", `chip ${cls}`);
      ch.append(icon(ico), document.createTextNode(text));
      if (title) ch.title = title;
      line.append(ch);
    };
    const ends = sel.attributes?.mode_ends_at;
    if (ends) {
      // In the house's time zone, like the schedules (computed by the server):
      // a browser in another zone would otherwise show another hour.
      const at = new Date(ends).toLocaleTimeString(LANG, {
        hour: "2-digit", minute: "2-digit", timeZone: this._hass.config?.time_zone || undefined,
      });
      chip("timer", "mdi:timer-outline", T.statusTimer(sel.attributes.return_mode, at));
    }
    if (st[ids.lock]?.state === "on") {
      chip("lock", "mdi:lock-outline", T.statusLocked(st[c.entity_id]?.attributes?.memory));
    }
    const name = (e) => st[e]?.attributes?.friendly_name || e;
    for (const e of c.exclusion || []) {
      if (st[e]?.state === "on") chip("safety", "mdi:shield-alert-outline", name(e), T.exclusion);
    }
    for (const e of c.inhibition || []) {
      if (st[e]?.state === "on") chip("inhib", "mdi:pause-circle-outline", name(e), T.inhibition);
    }
    return line;
  }

  /** The cover's morning and evening actions with today's times, the next
   *  one marked, then how the cover's state now changes that next one.
   *  Empty when the cover follows no schedule that is on. */
  _schedLine(c) {
    const house = this._cfg.schedule || {};
    const acts = c.schedule || {};
    // Morning first, evening second. A schedule that is off is left out; one
    // that is on but does nothing on this cover says so. None of the
    // schedules that are on acting on this cover: no row.
    const action = (k) => (house[k] ? acts[k] ?? null : null);
    if (!SCHED_KINDS.some((k) => action(k) != null)) return [];
    const day = this._hass.states[this._cfg.day_entity]?.attributes || {};
    const at = { morning: day.opening, evening: day.closing };
    const next = day.next_change;
    // next_change is today's opening, today's closing, or tomorrow's opening.
    const nextKind = !next ? null : next === day.closing ? "evening" : "morning";
    const tomorrow = !!next && next !== day.opening && next !== day.closing;
    // In the house's time zone, like the schedules (computed by the server).
    const hm = (iso) => new Date(iso).toLocaleTimeString(LANG, {
      hour: "2-digit", minute: "2-digit", timeZone: this._hass.config?.time_zone || undefined,
    });

    const row = el("button", "sched-row");
    row.type = "button";
    row.title = T.schedOpen;
    row.setAttribute("aria-label", T.schedAria(this._coverName(c)));
    // The rest of the card opens the cover's editor: this row opens the tab.
    row.addEventListener("keydown", (e) => e.stopPropagation());
    row.addEventListener("click", (e) => {
      e.stopPropagation();
      if (!this._leaveEditor()) return;
      this._tab = "horaires";
      if (nextKind) this._schedKind = nextKind;
      this._render();
    });
    for (const k of SCHED_KINDS) {
      if (!house[k]) continue;
      const a = action(k);
      const isNext = a != null && nextKind === k;
      const done = a != null && !isNext && !!at[k] && new Date(at[k]) <= new Date();
      const cell = el("span", `ev${a == null ? " none" : isNext ? " next" : done ? " done" : ""}`);
      row.append(cell);
      const time = el("span", "t");
      time.append(icon(k === "morning" ? "mdi:weather-sunset-up" : "mdi:weather-sunset-down"));
      const when = isNext && tomorrow ? T.schedTomorrow(hm(next)) : at[k] ? hm(at[k]) : "";
      if (when) time.append(el("b", "", when));
      if (isNext) time.title = T.schedNext;
      const act = el("span", "a");
      cell.append(time, act);
      if (a == null) {
        act.append(el("span", "lbl", T.schedNone));
      } else if (typeof a === "object") {
        const g = icon(a.force ? "mdi:flash" : "mdi:lock-outline", a.force ? "k-now" : "k-mem");
        g.title = a.force ? T.sched.forcePos : T.sched.keepLock;
        act.append(el("span", "lbl", `${a.position} %`), g);
      } else {
        const dot = el("span", "dot");
        dot.style.background = this._cfg.modes.find((m) => m.name === a)?.color || "var(--secondary-text-color)";
        act.append(dot, el("span", "lbl", a));
      }
    }
    const hint = this._schedForecast(c, nextKind ? action(nextKind) : null);
    return hint ? [row, hint] : [row];
  }

  /** What the cover's state now changes at its next schedule, or null:
   *  the same rules as the server (see async_request_mode and
   *  _set_cover_position_impl), read from the live states. */
  _schedForecast(c, a) {
    if (a == null) return null;
    const st = this._hass.states;
    const ids = this._cfg.helpers?.[c.entity_id] || {};
    const cur = st[ids.select]?.state;
    const curMode = this._cfg.modes.find((m) => m.name === cur);
    const name = (e) => st[e]?.attributes?.friendly_name || e;
    const isPos = typeof a === "object";
    const target = isPos ? null : this._cfg.modes.find((m) => m.name === a);
    if (!isPos && a === cur) return null;
    const safety = (c.exclusion || []).find((e) => st[e]?.state === "on");
    const inhib = (c.inhibition || []).find((e) => st[e]?.state === "on");
    let kind, ico, text;
    if (!isPos && cur && (target?.spares || []).includes(cur)) {
      [kind, ico, text] = ["wait", "mdi:timer-sand", curMode?.duration ? T.fcAfterTimed(cur, a) : T.fcSpared(cur, a)];
    } else if (safety) {
      [kind, ico, text] = ["wait", "mdi:shield-alert-outline", T.fcSafety(name(safety))];
    } else if (isPos && !a.force && st[ids.lock]?.state === "on") {
      [kind, ico, text] = ["mem", "mdi:lock-outline", T.fcMemory(a.position)];
    } else if (inhib && !(isPos ? a.force : target?.priority)) {
      [kind, ico, text] = ["wait", "mdi:pause-circle-outline", T.fcInhib(name(inhib))];
    } else if (isPos && a.force && curMode?.behavior) {
      [kind, ico, text] = ["warn", "mdi:alert-outline", T.fcRecompute];
    } else {
      return null;
    }
    const p = el("p", `sched-hint ${kind}`);
    p.append(icon(ico), el("span", "", text));
    return p;
  }

  /** Behavior keys the cover overrides — the amber count on its card.
   *  An override is a departure FROM something: without a template every value
   *  is stored locally by definition, so counting them would report the whole
   *  field list as deviations and mark nothing, which is what _behaviorRow
   *  already (correctly) does. No template, no count. */
  _overrideCount(item) {
    if (!this._templateOf(item)) return 0;
    const fields = this._cfg.behavior?.fields || {};
    return Object.keys(fields).filter(
      (k) => fields[k].type !== "boolean" && Object.prototype.hasOwnProperty.call(item, k)
    ).length;
  }

  _coverEditor(wrap) {
    const { idx, draft } = this._edit;
    const creating = idx < 0;
    const rerender = () => { this._render(); };

    const tpl = this._templateOf(draft);
    const baseline = this._baseline(draft);

    /* A bar that stays on top of the long page: the way back, then one stop
       per section, those holding overrides marked. */
    const nav = el("nav", "ed-nav");
    const back = el("button", "btn ghost");
    back.type = "button";
    back.append(icon("mdi:arrow-left"), document.createTextNode(T.backToCovers));
    back.addEventListener("click", () => { if (this._leaveEditor()) this._render(); });
    const stops = el("div", "stops");
    nav.append(back, stops);
    wrap.append(nav);
    const navDots = {};
    const stop = (key, label, target) => {
      const b = el("button", "", label);
      b.type = "button";
      b.addEventListener("click", () => target.scrollIntoView({ behavior: "smooth", block: "start" }));
      stops.append(b);
      navDots[key] = b;
    };

    /* identity: which cover, on which wall, from which template, and what it
       is doing right now */
    const idCard = el("section", "card ed-anchor");
    const grid = el("div", "ed-ident");
    const plate = el("div", "ed-plate");
    plate.append(draft.entity_picture ? this._coverPic(draft) : icon("mdi:window-shutter"));
    const line2 = el("div", "line2");
    // The picture is set once: a link until there is one.
    if (draft.entity_picture || this._picOpen) {
      const picLabel = el("span", "ed-lbl", T.picture);
      picLabel.style.margin = "0";
      line2.append(picLabel, this._edInput(draft.entity_picture,
        (v) => { draft.entity_picture = v || undefined; }, "small", T.picturePh));
    } else {
      const addPic = el("button", "linkbtn");
      addPic.type = "button";
      addPic.append(icon("mdi:image-plus-outline"), document.createTextNode(T.addPicture));
      addPic.addEventListener("click", () => { this._picOpen = true; rerender(); });
      line2.append(addPic);
    }
    // The live state is read off the SAVED cover: its helper entities are the
    // ones that exist, whatever the draft now points at.
    const status = creating ? null : this._statusLine(this._cfg.covers[idx]);
    if (status) line2.append(status);
    grid.append(plate,
      this._labeled(T.entity, this._haSelector({ entity: { domain: ["cover"] } },
        draft.entity_id || undefined, (v) => { draft.entity_id = v || ""; }), "wide"),
      this._facadeField(draft, rerender),
      this._templateField(draft, rerender),
      line2);
    idCard.append(grid);
    // A template for another type of window than the facade's: the server refuses it.
    const facKind = tiltKind(facadeTilt(this._cfg.facades.find((f) => f.name === draft.facade)));
    if (tpl && templateKind(tpl) !== facKind) {
      idCard.append(this._warnNote(T.tplKindMismatch(tpl.name, T.kindNoun[templateKind(tpl)], T.kindNoun[facKind])));
    }
    wrap.append(idCard);
    stop("cover", T.nav.cover, idCard);

    /* its row of the matrix, and its schedules: what it does in each mode,
       changed here with the matrix's own editor, saved with the cover */
    const modesCard = this._edCard("mdi:view-grid-outline", T.coverModesTitle);
    modesCard.classList.add("ed-anchor");
    modesCard.style.marginTop = "var(--fp-s4)";
    const see = el("button", "linkbtn end");
    see.type = "button";
    see.append(document.createTextNode(T.seeMatrix));
    see.addEventListener("click", () => {
      if (!this._leaveEditor()) return;
      this._tab = "matrice";
      this._render();
    });
    modesCard.querySelector("h3").append(see);
    const cells = el("div", "m-cells ed-cells");
    for (const mode of this._cfg.modes) {
      const item = el("div", "m-item");
      const lab = el("span", "m-lab");
      const dot = el("span", "dot");
      dot.style.background = mode.color || "#888888";
      lab.append(dot, el("span", "", mode.name));
      item.append(lab, this._cellNode(draft, mode, (value) => {
        draft.modes = { ...(draft.modes || {}) };
        if (value === null) delete draft.modes[mode.name];
        else draft.modes[mode.name] = value;
        rerender();
      }));
      cells.append(item);
    }
    modesCard.append(cells);
    if (!creating) {
      const sched = this._schedLine(this._cfg.covers[idx]);
      if (sched.length) {
        const box = el("div", "ed-sched");
        box.append(el("span", "ed-lbl", T.schedTitle), ...sched);
        modesCard.append(box);
      }
    }
    wrap.append(modesCard);
    stop("modes", T.nav.modes, modesCard);

    /* what holds it back: safety stops and pauses, side by side */
    const prot = this._edCard("mdi:shield-half-full", T.blockTitle, T.blockSub);
    prot.classList.add("ed-anchor");
    prot.style.marginTop = "var(--fp-s4)";
    const both = el("div", "prot");
    const block = (cls, ico, title, sub, ex, key) => {
      const b = el("div", cls);
      const h = el("h4");
      h.append(icon(ico), el("span", "", title));
      const body = el("div", "pbody");
      body.append(el("p", "", sub),
        this._entityChips(draft[key] || [], (list) => { draft[key] = list; rerender(); }),
        el("p", "ex", ex));
      b.append(h, body);
      return b;
    };
    both.append(
      block("safety", "mdi:shield-alert-outline", T.safetyTitle, T.safetySub, T.safetyEx, "exclusion"),
      block("pause", "mdi:pause-circle-outline", T.pauseTitle, T.pauseSub, T.pauseEx, "inhibition"));
    prot.append(both);
    wrap.append(prot);
    stop("block", T.nav.block, prot);

    /* how the position is computed, section by section: one sentence says
       where the values come from and how many this cover overrides */
    const schema = this._cfg.behavior;
    if (schema) {
      const head = el("div", "ed-head");
      const titles = el("div");
      titles.append(el("h2", "", T.calcTitle));
      const from = el("p", "calc-from");
      titles.append(from);
      head.append(titles);
      let cols = null;
      let onCount = null;
      if (tpl) {
        const go = el("button", "linkbtn");
        go.type = "button";
        go.title = T.openTemplate;
        go.append(document.createTextNode(tpl.name));
        go.addEventListener("click", () => {
          if (!this._leaveEditor()) return;
          const i = this._cfg.templates.findIndex((t) => t.name === tpl.name);
          this._tab = "maison";
          this._openEditor({ section: "template", idx: i, draft: { ...this._cfg.templates[i] } });
          this._render();
        });
        const except = el("span");
        from.append(document.createTextNode(`${T.calcFrom} `), go, except);
        const empty = this._note(T.noOwn);
        empty.hidden = true;
        const filter = el("div", "seg own-filter");
        const all = el("button", "", T.filterAll);
        const only = el("button");
        for (const b of [all, only]) b.type = "button";
        let count = 0;
        const setFilter = (on) => {
          this._ownOnly = on;
          all.classList.toggle("on", !on);
          only.classList.toggle("on", on);
          all.setAttribute("aria-pressed", String(!on));
          only.setAttribute("aria-pressed", String(on));
          cols?.classList.toggle("own-only", on);
          empty.hidden = !(on && count === 0);
        };
        all.addEventListener("click", () => setFilter(false));
        only.addEventListener("click", () => setFilter(true));
        filter.append(all, only);
        onCount = (n, per = {}) => {
          count = n;
          except.replaceChildren();
          if (n) {
            const chip = el("span", "chip ovr");
            chip.append(icon("mdi:pencil-outline"), document.createTextNode(T.overrides(n)));
            except.append(document.createTextNode(`${T.calcExcept} `), chip);
          } else {
            except.append(document.createTextNode(T.calcNoOwn));
          }
          only.textContent = T.filterOwn(n);
          empty.hidden = !(this._ownOnly && n === 0);
          for (const [k, b] of Object.entries(navDots)) b.classList.toggle("has-own", !!per[k]);
        };
        head.append(el("span", "spacer"), filter);
        cols = this._behaviorGrid(schema.sections, draft, baseline, tpl.name, onCount);
        setFilter(!!this._ownOnly);
        wrap.append(head, empty, cols);
      } else {
        from.textContent = T.noTplChip;
        cols = this._behaviorGrid(schema.sections, draft, baseline, null);
        wrap.append(head, cols);
      }
      // In the order the computation reads them, not the columns': the
      // window, where the sun must be, then what is done with it.
      for (const { key } of schema.sections) {
        const card = cols.querySelector(`.sect[data-key="${key}"]`);
        if (!card) continue;
        card.classList.add("ed-anchor");
        stop(key, T.nav[key] || T.sections[key] || key, card);
      }
      // The first count ran before the stops existed: mark them now.
      if (tpl) {
        for (const card of cols.querySelectorAll(".sect")) {
          navDots[card.dataset.key]?.classList.toggle("has-own", !!card.querySelector(".numf.ovr"));
        }
      }
    }

    wrap.append(this._saveBar(() => {
      const items = this._cfg.covers.map((c) => JSON.parse(JSON.stringify(c)));
      if (creating) items.push(draft); else items[idx] = draft;
      this._saveSection("cover", items);
    }, creating ? null : {
      onDelete: () => this._saveSection("cover", this._cfg.covers.filter((_, i) => i !== idx)
        .map((c) => JSON.parse(JSON.stringify(c)))),
    }));
  }

  /* ---------- HORAIRES ---------- */

  /** Editing copy of the house's schedules and of each cover's morning / evening mode. */
  _newSchedDraft() {
    const house = this._cfg.schedule || {};
    const defaults = this._cfg.schedule_defaults || {};
    const draft = { enabled: {}, s: {}, assign: {} };
    for (const k of SCHED_KINDS) {
      draft.enabled[k] = !!house[k];
      // The defaults come from the server; the last fallback only keeps an
      // older backend that sends none from breaking the tab.
      draft.s[k] = schedFromCfg(house[k] || defaults[k]
        || { type: "fixed", time: k === "morning" ? "07:30" : "20:30" }, k);
    }
    for (const c of this._cfg.covers) {
      draft.assign[c.entity_id] = { morning: c.schedule?.morning ?? null, evening: c.schedule?.evening ?? null };
    }
    return draft;
  }

  /** Ask the server for the curve; one request in flight per schedule, the last one wins. */
  _schedRequest(kind, onDone) {
    this._schedReq = this._schedReq || {};
    const r = this._schedReq[kind] || (this._schedReq[kind] = { busy: false, again: false });
    if (r.busy) { r.again = true; return; }
    r.busy = true;
    this._hass.connection.sendMessagePromise({
      type: WS_SCHED_PREVIEW, kind, settings: schedToCfg(this._schedDraft.s[kind]),
    }).then((res) => {
      this._schedPv = this._schedPv || {};
      this._schedPv[kind] = res;
      onDone();
    }).catch((err) => console.error(`${DOMAIN}: schedule preview failed`, err))
      .finally(() => {
        r.busy = false;
        if (r.again) { r.again = false; this._schedRequest(kind, onDone); }
      });
  }

  _renderSchedules(wrap) {
    const draft = this._schedDraft || (this._schedDraft = this._newSchedDraft());
    if (this._schedClean == null) this._schedClean = JSON.stringify(draft);
    const kind = this._schedKind || (this._schedKind = "evening");
    const W = T.sched;
    const s = draft.s[kind];
    this._schedPv = this._schedPv || {};

    const lead = el("p", "ed-note sched-lead");
    lead.append(icon("mdi:information-outline"), el("span", "", W.introShort), this._info(W.introInfo));
    wrap.append(lead);

    /* ---- today, at a glance: one card per schedule, its switch, today's
       time and what it does to the covers. A card picks the schedule whose
       time is set further down. ---- */
    const sum = el("div", "sched-sum");
    const kTimes = {};
    const kRefs = {};
    const kEffects = {};
    for (const k of SCHED_KINDS) {
      const c = el("div", `card sched-k${k === kind ? " on" : ""}${draft.enabled[k] ? "" : " off"}`);
      c.setAttribute("role", "button");
      c.tabIndex = 0;
      c.setAttribute("aria-pressed", String(k === kind));
      const pick = () => { if (this._schedKind !== k) { this._schedKind = k; this._render(); } };
      c.addEventListener("click", pick);
      c.addEventListener("keydown", (e) => { if (e.target === c && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); pick(); } });
      const top = el("div", "sk-top");
      const sw = this._switch(draft.enabled[k], (v) => { draft.enabled[k] = v; this._render(); }, W.enable[k]);
      sw.addEventListener("click", (e) => e.stopPropagation());
      top.append(icon(k === "morning" ? "mdi:weather-sunset-up" : "mdi:weather-sunset-down"),
        el("span", "sk-title", W.kinds[k]), el("span", "spacer"), sw);
      kTimes[k] = el("span", "sk-time");
      kRefs[k] = el("span", "sk-ref");
      const when = el("div", "sk-when");
      when.append(kTimes[k], kRefs[k]);
      kEffects[k] = el("div", "sk-eff");
      c.append(top, when, kEffects[k]);
      sum.append(c);
    }
    wrap.append(sum);

    /* ---- the time of the chosen schedule ---- */
    const card = el("div", "card sched blk");
    const head = el("div", "sched-head");
    const refText = el("span");
    const ref = el("span", "sched-ref");
    ref.append(icon("mdi:weather-sunset"), refText);
    const ttl = el("h3", "sec", W.curveTitle[kind]);
    ttl.style.margin = "0";
    head.append(ttl, ref);
    card.append(head);
    if (!draft.enabled[kind]) card.append(this._note(W.enableHint[kind]));

    const body = el("div", "sched-body");
    body.hidden = !draft.enabled[kind];
    card.append(body);

    /* the six settings, in three groups: the curve, its bounds, the crossings */
    const groups = el("div", "sched-groups");
    const group = (iconName, title) => {
      const g = el("div", "sgrp");
      const h = el("h4");
      h.append(icon(iconName), el("span", "", title));
      g.append(h);
      groups.append(g);
      return g;
    };
    const gCurve = group("mdi:chart-bell-curve-cumulative", W.grpCurve);
    const curveInfo = this._info(W.fixedHint);  // completed by the DST gap once the curve is known
    gCurve.querySelector("h4").append(curveInfo);
    const curvePair = el("div", "spair");
    gCurve.append(curvePair);
    const gBounds = group("mdi:arrow-collapse-vertical", W.grpBounds);
    const boundsPair = el("div", "spair");
    gBounds.append(boundsPair);
    const gFine = group("mdi:tune-vertical", W.grpFine);
    // The crossings are rarely touched: folded, unless one of them is on.
    const fine = document.createElement("details");
    fine.className = "sfine";
    fine.open = this._schedFineOpen ?? (s.x1.on || s.x2.on);
    fine.addEventListener("toggle", () => { this._schedFineOpen = fine.open; });
    const fineSum = document.createElement("summary");
    const finePair = el("div", "spair one");
    fine.append(fineSum, finePair);
    gFine.append(fine);

    const mkField = (parent, color, label, type, toggle) => {
      const box = el("div", "sf");
      box.style.setProperty("--c", color);
      const top = el("div", "sf-top");
      const lab = el("label", "", label);
      top.append(lab);
      let cb = null;
      if (toggle) {
        cb = document.createElement("input");
        cb.type = "checkbox";
        cb.setAttribute("role", "switch");
        cb.setAttribute("aria-label", label);
        top.append(cb);
      }
      const input = document.createElement("input");
      input.type = type;
      const info = el("span", "sf-info");
      box.append(top, input, info);
      parent.append(box);
      return { box, input, cb, info, lab };
    };
    const F = {
      hi: mkField(curvePair, "var(--ce-h)", W.hi, "time"),
      lo: mkField(curvePair, "var(--ce-h)", W.lo, "time"),
      fl: mkField(boundsPair, "var(--ce-clamp)", W.fl, "time", true),
      ce: mkField(boundsPair, "var(--ce-clamp)", W.ce, "time", true),
      x1: mkField(finePair, "var(--ce-x)", W.x1, "date", true),
      x2: mkField(finePair, "var(--ce-x)", W.x2, "date", true),
    };
    body.append(groups);
    const howTo = el("p", "ed-note");
    howTo.append(icon("mdi:gesture-tap-hold"), el("span", "", W.dragHint));
    body.append(howTo);

    const legend = el("div", "legend sched-legend");
    body.append(legend);
    const chart = el("div", "sched-chart");
    const NS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("role", "img");
    const tip = el("div", "sched-tip");
    tip.hidden = true;
    chart.append(svg, tip);
    body.append(chart);
    const warn = el("div", "sched-warn");
    body.append(warn);
    const stats = el("div", "sched-stats");
    // Shown only when the curve runs ahead of the sun on some days.
    const before = el("p", "sched-hint warn");
    body.append(stats, before);

    const bar = this._saveBar(() => {
      const house = {};
      for (const k of SCHED_KINDS) if (draft.enabled[k]) house[k] = schedToCfg(draft.s[k]);
      this._saveSection("schedule", { house, covers: draft.assign });
    });
    // A drag moves the draft from pointermove: the bar is told directly.
    const touch = () => this._syncSaveBar?.();

    /* ---- per-cover mode ---- */
    const tcard = el("div", "card blk");
    const thead3 = el("div", "toolbar");
    thead3.style.margin = "0 0 var(--fp-s2)";
    const title = el("h3", "sec", W.perCover);
    title.style.margin = "0";
    const diffLegend = el("span", "sched-diff-legend");
    diffLegend.append(el("i", "sw-diff"), document.createTextNode(W.differs));
    thead3.append(title, el("span", "spacer"), diffLegend, this._info(W.perCoverSub));
    tcard.append(thead3);
    const scroll = el("div", "t-scroll");
    const table = el("table", "assign");
    const hr = el("tr");
    const timeCells = {};
    hr.append(el("th", "", W.cover));
    for (const k of SCHED_KINDS) { timeCells[k] = el("th"); hr.append(timeCells[k]); }
    const thead = el("thead"); thead.append(hr); table.append(thead);
    const timed = new Set(this._cfg.modes.filter((m) => m.duration).map((m) => m.name));
    const offered = (c) => Object.keys(c.modes || {}).filter((m) => !timed.has(m));
    const colorOf = (n) => this._cfg.modes.find((m) => m.name === n)?.color;
    const tbody = el("tbody");
    // An action is a mode name, a position {position, force}, or null.
    const POS = "\u0001position";
    const akey = (v) => (v == null ? "" : typeof v === "object" ? `p:${v.position}:${v.force ? 1 : 0}` : `m:${v}`);
    // A cover with a shading or solar gain mode: a forced position may be
    // moved again by the next computation.
    const computes = (c) => Object.keys(c.modes || {})
      .some((n) => this._cfg.modes.find((m) => m.name === n)?.behavior);
    const cells = { morning: [], evening: [] };
    const allCell = {};

    /** One schedule cell: the list (none, the modes, a position) and, for a
     *  position, its value and whether it respects the lock or forces it.
     *  get() returns undefined when the "all covers" row has several values. */
    const mkCell = (k, modes, label, get, set, flagged, all = false) => {
      const box = el("div", "sact");
      const sel = document.createElement("select");
      sel.className = "fselect msel";
      sel.setAttribute("aria-label", label);
      const add = (parent, val, text) => {
        const o = document.createElement("option");
        o.value = val;
        o.textContent = text;
        parent.append(o);
        return o;
      };
      if (all) add(sel, "*", W.mixed).disabled = true;
      add(sel, "", W.noneOpt);
      if (modes.length) {
        const g = document.createElement("optgroup");
        g.label = W.grpMode;
        for (const n of modes) add(g, n, n);
        sel.append(g);
      }
      const gp = document.createElement("optgroup");
      gp.label = W.grpPos;
      add(gp, POS, W.posOpt);
      sel.append(gp);

      const pos = el("div", "spos");
      const num = document.createElement("input");
      num.type = "number";
      num.min = "0";
      num.max = "100";
      num.step = "1";
      num.setAttribute("aria-label", `${W.posLabel}, ${label}`);
      const seg = el("div", "seg spos-seg");
      seg.setAttribute("role", "group");
      seg.setAttribute("aria-label", `${W.lockedLabel}, ${label}`);
      const mkBtn = (force, iconName, text, hint) => {
        const b = el("button");
        b.type = "button";
        b.title = hint;
        b.append(icon(iconName), el("span", "", text));
        b.addEventListener("click", () => { set({ ...get(), force }); refreshKind(k); touch(); });
        seg.append(b);
        return b;
      };
      const bKeep = mkBtn(false, "mdi:lock-outline", W.keepLock, W.keepLockHint);
      const bForce = mkBtn(true, "mdi:flash", W.forcePos, W.forceHint);
      const flag = icon("mdi:alert-outline", "sflag");
      flag.title = W.forceComputes;
      flag.setAttribute("role", "img");
      flag.setAttribute("aria-label", W.forceComputes);
      pos.append(num, el("span", "spct", "%"), seg, flag);
      box.append(sel, pos);

      const off = !draft.enabled[k];
      for (const c of [sel, num, bKeep, bForce]) c.disabled = off;

      const show = () => {
        const v = get();
        const p = v && typeof v === "object" ? v : null;
        sel.value = v === undefined ? "*" : p ? POS : v ?? "";
        // The mode's own colour on the edge of the list, as on the matrix.
        sel.style.borderLeftColor = p ? "var(--secondary-text-color)" : (typeof v === "string" && colorOf(v)) || "";
        sel.classList.toggle("none", v === null);
        pos.hidden = !p;
        if (!p) return;
        if (document.activeElement !== num) num.value = String(p.position);
        for (const [b, on] of [[bKeep, !p.force], [bForce, p.force]]) {
          b.classList.toggle("on", on);
          b.setAttribute("aria-pressed", String(on));
        }
        flag.hidden = !(p.force && flagged());
      };
      sel.addEventListener("change", () => {
        const cur = get();
        if (sel.value === POS) set(cur && typeof cur === "object" ? cur : { position: k === "morning" ? 100 : 0, force: false });
        else set(sel.value || null);
        refreshKind(k);
        touch();
      });
      num.addEventListener("input", () => {
        // An empty box is a transient state while typing, not a zero.
        if (num.value === "") return;
        const n = Math.max(0, Math.min(100, Math.round(Number(num.value))));
        if (!Number.isFinite(n)) return;
        set({ ...get(), position: n });
        refreshKind(k);
        touch();
      });
      // Leaving the box shows the value kept (clamped, or back from empty).
      num.addEventListener("blur", show);
      return { box, show };
    };

    // What a schedule does to the covers, as its summary card tells it: the
    // most common action first, with how many covers take it.
    const paintEffects = (k) => {
      if (!draft.enabled[k]) { kEffects[k].replaceChildren(el("span", "", W.enableHint[k])); return; }
      const by = new Map();
      for (const c of this._cfg.covers) {
        const v = draft.assign[c.entity_id][k] ?? null;
        const label = v == null ? W.effNone : typeof v === "object" ? `${v.position} %` : v;
        by.set(label, (by.get(label) || 0) + 1);
      }
      kEffects[k].replaceChildren(...[...by].sort((x, y) => y[1] - x[1]).map(([label, n]) => {
        const part = el("span");
        const color = colorOf(label);
        if (color) {
          const dot = el("span", "mdot");
          dot.style.background = color;
          part.append(dot);
        }
        part.append(document.createTextNode(W.effPart(label, T.covers(n))));
        return part;
      }));
    };

    // What most covers do is the norm; a cover that does something else is marked.
    const refreshKind = (k) => {
      const count = new Map();
      for (const c of this._cfg.covers) {
        const key = akey(draft.assign[c.entity_id][k]);
        count.set(key, (count.get(key) || 0) + 1);
      }
      const norm = [...count].sort((a, b) => b[1] - a[1])[0]?.[0] ?? "";
      for (const { cell, c } of cells[k]) {
        cell.box.classList.toggle("diff", akey(draft.assign[c.entity_id][k]) !== norm);
        cell.show();
      }
      allCell[k].show();
      paintEffects(k);
    };

    /* the "all covers" row: one choice applied to every cover that offers it */
    const allRow = el("tr", "all");
    const allName = el("td");
    const allHead = el("div", "rowh");
    const pic = el("span", "pic");
    pic.append(icon("mdi:home-outline"));
    allHead.append(pic, el("span", "nm", W.allCovers));
    allName.append(allHead);
    allRow.append(allName);
    const union = this._cfg.modes.map((m) => m.name)
      .filter((n) => this._cfg.covers.some((c) => offered(c).includes(n)));
    for (const k of SCHED_KINDS) {
      const td = el("td");
      const common = () => {
        const keys = new Set(this._cfg.covers.map((c) => akey(draft.assign[c.entity_id][k])));
        return keys.size === 1 ? draft.assign[this._cfg.covers[0].entity_id][k] ?? null : undefined;
      };
      const setAll = (v) => {
        for (const c of this._cfg.covers) {
          if (typeof v === "string" && !offered(c).includes(v)) continue;
          draft.assign[c.entity_id][k] = v && typeof v === "object" ? { ...v } : v;
        }
      };
      allCell[k] = mkCell(k, union, `${W.kinds[k]}, ${W.allCovers}`, common, setAll,
        () => this._cfg.covers.some(computes), true);
      td.append(allCell[k].box);
      allRow.append(td);
    }
    tbody.append(allRow);

    /* one row per cover, grouped by facade like the matrix */
    for (const [facade, covers] of this._grouped()) {
      if (!covers.length) continue;
      const fr = el("tr", "fac");
      const ftd = el("td", "", facade ? `${T.facade} ${facade}` : T.noFacade);
      ftd.colSpan = 1 + SCHED_KINDS.length;
      fr.append(ftd);
      tbody.append(fr);
      for (const c of covers) {
        const tr = el("tr");
        const th = el("td");
        const rowh = el("div", "rowh");
        rowh.append(this._coverPic(c), el("span", "nm", this._coverName(c)));
        th.append(rowh);
        tr.append(th);
        for (const k of SCHED_KINDS) {
          const td = el("td");
          const cell = mkCell(k, offered(c), `${W.kinds[k]}, ${this._coverName(c)}`,
            () => draft.assign[c.entity_id][k] ?? null,
            (v) => { draft.assign[c.entity_id][k] = v; },
            () => computes(c));
          cells[k].push({ cell, c });
          td.append(cell.box);
          tr.append(td);
        }
        tbody.append(tr);
      }
    }
    for (const k of SCHED_KINDS) refreshKind(k);
    table.append(tbody);
    scroll.append(table);
    tcard.append(scroll);
    wrap.append(tcard, card, bar);

    /* ---- drawing ---- */
    // Drawn at the size it is shown: the width follows the card, the height
    // stays at 300 px, so the chart neither towers over a wide screen nor
    // scales its text up with it. Redrawn when the card's width changes.
    let Wd = 940;
    const Hd = 300, M = { l: 52, r: 104, t: 30, b: 34 };
    const [Y0, Y1] = SCHED_RANGE[kind];
    const mk = (t, a, p = svg) => { const e = document.createElementNS(NS, t); for (const k in a) e.setAttribute(k, a[k]); p.appendChild(e); return e; };
    const xOf = (j) => M.l + (j - 1) / 364 * (Wd - M.l - M.r);
    const yOf = (m) => M.t + (Y1 - m) / (Y1 - Y0) * (Hd - M.t - M.b);
    const mAt = (py) => Y1 - (py - M.t) / (Hd - M.t - M.b) * (Y1 - Y0);
    const jAt = (px) => Math.max(1, Math.min(365, Math.round((px - M.l) / (Wd - M.l - M.r) * 364 + 1)));
    const year = new Date().getFullYear();
    let clampMsg = "", cross = null;

    const pathOf = (arr) => {
      let d = "", p = null;
      for (let j = 1; j <= 365; j++) {
        const v = arr[j - 1];
        d += `${p === null || Math.abs(v - p) > 30 ? "M" : "L"}${xOf(j).toFixed(1)},${yOf(v).toFixed(1)}`;
        p = v;
      }
      return d;
    };
    const chip = (key, yy, color, label) => {
      const g = mk("g", { class: "handle", "data-k": key });
      const cx = Wd - M.r + 54, w = 96;
      mk("rect", { x: cx - w / 2, y: yy - 11, width: w, height: 22, rx: 11, fill: color, stroke: "var(--card-background-color)", "stroke-width": 1.5 }, g);
      mk("text", { x: cx, y: yy + 4, "text-anchor": "middle", class: "on-chip" }, g).textContent = label;
    };
    const hLine = (key, yy, color) => {
      const g = mk("g", { class: "handle", "data-k": key });
      mk("line", { x1: M.l, x2: Wd - M.r, y1: yy, y2: yy, stroke: color, "stroke-width": 1.5, "stroke-dasharray": key === "fl" || key === "ce" ? "2 3" : "6 4" }, g);
      mk("line", { x1: M.l, x2: Wd - M.r, y1: yy, y2: yy, stroke: "transparent", "stroke-width": 18 }, g);
    };
    const vHandle = (key, j, cy, ko) => {
      const xx = xOf(j), g = mk("g", { class: "handle", "data-k": key }), c = ko ? "var(--fp-warn)" : "var(--ce-x)";
      mk("line", { x1: xx, x2: xx, y1: M.t, y2: Hd - M.b, stroke: c, "stroke-width": 1.5, "stroke-dasharray": "6 4" }, g);
      mk("rect", { x: xx - 32, y: M.t - 26, width: 64, height: 20, rx: 10, fill: c }, g);
      mk("text", { x: xx, y: M.t - 12, "text-anchor": "middle", class: "on-chip" }, g).textContent = schedDayLabel(j, year, "short");
      mk("circle", { cx: xx, cy, r: 5, fill: c, stroke: "var(--card-background-color)", "stroke-width": 2 }, g);
      mk("line", { x1: xx, x2: xx, y1: M.t - 26, y2: Hd - M.b, stroke: "transparent", "stroke-width": 18 }, g);
    };

    const redraw = () => {
      Wd = Math.max(560, Math.round(chart.clientWidth || 940));
      svg.setAttribute("viewBox", `0 0 ${Wd} ${Hd}`);
      const pv = this._schedPv[kind];
      const sun = pv?.sun, pts = pv?.points;
      const fixed = s.hi === s.lo;
      svg.replaceChildren();
      for (let h = Math.ceil(Y0 / 60); h * 60 <= Y1; h++) {
        mk("line", { x1: M.l, x2: Wd - M.r, y1: yOf(h * 60), y2: yOf(h * 60), class: "grid" });
        mk("text", { x: M.l - 8, y: yOf(h * 60) + 4, "text-anchor": "end" }).textContent = `${h}:00`;
      }
      for (let i = 0; i < 12; i++) {
        const j = schedDayOfYear(year, i + 1, 1);
        if (i) mk("line", { x1: xOf(j), x2: xOf(j), y1: M.t, y2: Hd - M.b, class: "grid" });
        mk("text", { x: xOf(j + 14), y: Hd - M.b + 20, "text-anchor": "middle" }).textContent =
          new Intl.DateTimeFormat(LANG, { month: "short", timeZone: "UTC" }).format(new Date(Date.UTC(year, i, 15)));
      }
      if (sun) mk("path", { d: pathOf(sun), fill: "none", stroke: "var(--ce-b-shade)", "stroke-width": 2 });

      const msgs = [];
      if (pv?.error) msgs.push(W.errors[pv.error] || pv.error);
      if (clampMsg) msgs.push(clampMsg);
      for (const [name, reason] of Object.entries(pv?.ignored || {})) {
        const j = name === "spring" ? s.x1.j : s.x2.j;
        msgs.push(W.ignored[reason]?.(schedDayLabel(j, year, "long"), W.ref[kind],
          sun ? hmFmt(sun[j - 1]) : "") || reason);
      }
      let st = [];
      let beforeTxt = "";
      if (pts && sun) {
        let seg2 = [], nBefore = 0, nX = 0, prev = null, bMax = -1e9, bJ = 1, eJ = 1, lJ = 1;
        const flush = () => {
          if (seg2.length > 1) mk("polygon", { points: seg2.map((j) => `${xOf(j)},${yOf(sun[j - 1])}`).concat(seg2.slice().reverse().map((j) => `${xOf(j)},${yOf(pts[j - 1])}`)).join(" "), class: "band" });
          seg2 = [];
        };
        for (let j = 1; j <= 365; j++) {
          const d = pts[j - 1] - sun[j - 1], before = d < 0;
          if (before) { seg2.push(j); nBefore++; } else flush();
          if (-d > bMax) { bMax = -d; bJ = j; }
          if (pts[j - 1] < pts[eJ - 1]) eJ = j;
          if (pts[j - 1] > pts[lJ - 1]) lJ = j;
          if (prev !== null && before !== prev) nX++;
          prev = before;
        }
        flush();
        mk("path", { d: pathOf(pts), fill: "none", stroke: "var(--primary-color)", "stroke-width": 2.5, "stroke-linejoin": "round" });
        const JP = pv.max_day, JT = pv.min_day;
        for (const [j, v] of [[JP, s.hi], [JT, fixed ? s.hi : s.lo]]) {
          const ya = Math.max(M.t, Math.min(Hd - M.b, yOf(v))), yb = yOf(sun[j - 1]), xx = xOf(j) - 10, d = v - sun[j - 1];
          mk("line", { x1: xx, x2: xx, y1: ya, y2: yb, class: "brk" });
          for (const yy of [ya, yb]) mk("line", { x1: xx - 4, x2: xx + 4, y1: yy, y2: yy, class: "brk" });
          const ty = (ya + yb) / 2 + (Math.abs(ya - yb) < 14 ? (d >= 0 ? -16 : 16) : 4);
          mk("text", { x: xx - 7, y: ty, "text-anchor": "end", class: "brk-t" }).textContent = signedMin(d);
        }
        const today = pv.today;
        mk("circle", { cx: xOf(today), cy: yOf(pts[today - 1]), r: 4.5, fill: "var(--primary-color)", stroke: "var(--card-background-color)", "stroke-width": 2 });
        if (nX > 2) msgs.push(W.manyCross(W.ref[kind], nX));
        // Three figures; the gaps to the sun are drawn on the curve itself,
        // and days ahead of the sun only get a word when there are some.
        st = [
          [W.today, hmFmt(pts[today - 1]), `${W.ref[kind]} ${hmFmt(sun[today - 1])}`],
          [W.earliest, hmFmt(pts[eJ - 1]), W.onDate(schedDayLabel(eJ, year, "long"))],
          [W.latest, hmFmt(pts[lJ - 1]), W.onDate(schedDayLabel(lJ, year, "long"))],
        ];
        beforeTxt = nBefore ? W.beforeRef(W.band[kind], nBefore, signedMin(-bMax), schedDayLabel(bJ, year, "long")) : "";
      }
      warn.hidden = !msgs.length;
      warn.replaceChildren(...msgs.map((m) => el("div", "", m)));
      before.hidden = !beforeTxt;
      before.replaceChildren(icon("mdi:alert-outline"), el("span", "", beforeTxt));
      stats.replaceChildren(...st.map(([k, v, t]) => {
        const d = el("div");
        d.append(el("span", "k", k), el("span", "v", v), el("span", "s", t));
        return d;
      }));

      const chips = [];
      if (fixed) {
        const yy = yOf(s.hi);
        hLine("both", yy, "var(--ce-h)");
        mk("text", { x: Wd - M.r - 6, y: yy - 7, "text-anchor": "end", class: "fixed-t" }).textContent = W.fixedLabel(hmFmt(s.hi));
        chips.push({ key: "hi", y0: yy, y: yy - 12, color: "var(--ce-h)", label: "▲ max" }, { key: "lo", y0: yy, y: yy + 12, color: "var(--ce-h)", label: "▼ min" });
      } else {
        hLine("hi", yOf(s.hi), "var(--ce-h)"); hLine("lo", yOf(s.lo), "var(--ce-h)");
        chips.push({ key: "hi", y0: yOf(s.hi), y: yOf(s.hi), color: "var(--ce-h)", label: `max ${hmFmt(s.hi)}` },
                   { key: "lo", y0: yOf(s.lo), y: yOf(s.lo), color: "var(--ce-h)", label: `min ${hmFmt(s.lo)}` });
      }
      if (s.fl.on) { hLine("fl", yOf(s.fl.m), "var(--ce-clamp)"); chips.push({ key: "fl", y0: yOf(s.fl.m), y: yOf(s.fl.m), color: "var(--ce-clamp)", label: `${W.flShort} ${hmFmt(s.fl.m)}` }); }
      if (s.ce.on) { hLine("ce", yOf(s.ce.m), "var(--ce-clamp)"); chips.push({ key: "ce", y0: yOf(s.ce.m), y: yOf(s.ce.m), color: "var(--ce-clamp)", label: `${W.ceShort} ${hmFmt(s.ce.m)}` }); }
      chips.sort((a, b) => a.y - b.y || (a.key === "hi" ? -1 : 1));
      for (let i = 1; i < chips.length; i++) chips[i].y = Math.max(chips[i].y, chips[i - 1].y + 24);
      const over = chips.length ? chips[chips.length - 1].y - (Hd - 12) : 0;
      if (over > 0) chips.forEach((c) => { c.y -= over; });
      for (let i = chips.length - 2; i >= 0; i--) chips[i].y = Math.min(chips[i].y, chips[i + 1].y - 24);
      for (const c of chips) {
        if (Math.abs(c.y - c.y0) > 1) mk("path", { d: `M${Wd - M.r},${c.y0} L${Wd - M.r + 6},${c.y}`, stroke: c.color, "stroke-width": 1.5, fill: "none" });
        chip(c.key, c.y, c.color, c.label);
      }
      if (!fixed && sun) {
        for (const k of ["x1", "x2"]) if (s[k].on) vHandle(k, s[k].j, yOf(sun[s[k].j - 1]), !!pv?.ignored?.[k === "x1" ? "spring" : "autumn"]);
      }
      cross = mk("line", { y1: M.t, y2: Hd - M.b, class: "cross", visibility: "hidden" });

      /* fields */
      const G = pv?.dst_gap || 0;
      curveInfo.title = W.fixedHint + (G ? W.dstHint(G / 60) : "");
      curveInfo.setAttribute("aria-label", curveInfo.title);
      fineSum.replaceChildren(icon("mdi:chevron-down", "chev-d"), el("span", "", W.crossSum(
        s.x1.on && !fixed ? schedDayLabel(s.x1.j, year, "short") : W.no,
        s.x2.on && !fixed ? schedDayLabel(s.x2.j, year, "short") : W.no)));
      refText.textContent = W.follows(W.refLong[kind], sun && pv ? hmFmt(sun[pv.today - 1]) : null);
      F.hi.lab.textContent = fixed ? W.hiFixed : W.hi;
      F.hi.input.value = hmFmt(s.hi); F.lo.input.value = hmFmt(s.lo);
      F.x1.input.value = schedDayToIso(s.x1.j, year); F.x2.input.value = schedDayToIso(s.x2.j, year);
      F.x1.cb.checked = s.x1.on; F.x2.cb.checked = s.x2.on;
      F.fl.input.value = hmFmt(s.fl.m); F.ce.input.value = hmFmt(s.ce.m);
      F.fl.cb.checked = s.fl.on; F.ce.cb.checked = s.ce.on;
      if (sun && pv) {
        F.hi.info.textContent = fixed ? W.fixedAll
          : `${schedDayLabel(pv.max_day, year, "short")} · ${signedMin(s.hi - sun[pv.max_day - 1])} / ${W.ref[kind]} ${hmFmt(sun[pv.max_day - 1])}`;
        F.lo.info.textContent = fixed ? W.glued
          : `${schedDayLabel(pv.min_day, year, "short")} · ${signedMin(s.lo - sun[pv.min_day - 1])} / ${W.ref[kind]} ${hmFmt(sun[pv.min_day - 1])}`;
      }
      for (const k of ["x1", "x2"]) {
        const ko = pv?.ignored?.[k === "x1" ? "spring" : "autumn"];
        F[k].info.textContent = fixed ? W.unusedFixed
          : s[k].on ? `${W.ref[kind]} ${sun ? hmFmt(sun[s[k].j - 1]) : ""}${ko ? W.ignoredShort : ""}` : W.offHalf;
        F[k].box.classList.toggle("off", fixed || !s[k].on);
        F[k].input.disabled = fixed || !s[k].on;
        F[k].cb.disabled = fixed;
      }
      for (const k of ["fl", "ce"]) {
        F[k].info.textContent = s[k].on ? W.legal : W.off;
        F[k].box.classList.toggle("off", !s[k].on);
        F[k].input.disabled = !s[k].on;
      }
      legend.replaceChildren(...[
        ["var(--primary-color)", W.kinds[kind], ""], ["var(--ce-b-shade)", W.refLongCap[kind], ""], ["", W.band[kind], "sw"],
      ].map(([c, t, cls]) => { const sp = el("span"); const i = el("i", `lg-line ${cls}`); if (c) i.style.background = c; sp.append(i, document.createTextNode(t)); return sp; }));

      /* times of the day in the table head */
      for (const k of SCHED_KINDS) {
        const p2 = this._schedPv[k];
        timeCells[k].textContent = draft.enabled[k] && p2?.points
          ? `${W.kinds[k]} · ${hmFmt(p2.points[p2.today - 1])}` : W.kinds[k];
        kTimes[k].textContent = !draft.enabled[k] ? W.offShort
          : p2?.points ? hmFmt(p2.points[p2.today - 1]) : "";
        kRefs[k].textContent = !draft.enabled[k] ? ""
          : W.follows(W.refLong[k], p2?.sun ? hmFmt(p2.sun[p2.today - 1]) : null);
      }
    };

    const refresh = () => this._schedRequest(kind, redraw);
    const changed = () => { redraw(); refresh(); touch(); };

    /* field input */
    const onTime = (key) => F[key].input.addEventListener("input", (e) => {
      if (!e.target.value) return;
      clampMsg = schedSetVal(this._schedPv[kind], s, key, hmParse(e.target.value), kind);
      changed();
    });
    ["hi", "lo", "fl", "ce"].forEach(onTime);
    for (const k of ["x1", "x2"]) {
      F[k].input.addEventListener("change", (e) => {
        if (!e.target.value) return;
        clampMsg = schedSetCross(this._schedPv[kind], s, k, schedIsoToDay(e.target.value, year), year);
        changed();
      });
      F[k].cb.addEventListener("change", (e) => { s[k].on = e.target.checked; clampMsg = ""; changed(); });
    }
    for (const k of ["fl", "ce"]) {
      F[k].cb.addEventListener("change", (e) => {
        s[k].on = e.target.checked;
        clampMsg = e.target.checked ? schedSetVal(this._schedPv[kind], s, k, s[k].m, kind) : "";
        changed();
      });
    }

    /* drag */
    const pt = (e) => { const p = svg.createSVGPoint(); p.x = e.clientX; p.y = e.clientY; return p.matrixTransform(svg.getScreenCTM().inverse()); };
    // The drag starts only past 3 px, so a double-click does not move the value.
    let drag = null, downAt = null, moved = false, lastKey = null;
    svg.addEventListener("pointerdown", (e) => {
      const h = e.target.closest(".handle");
      lastKey = h ? h.dataset.k : null;
      if (!h) return;
      drag = h.dataset.k; downAt = { x: e.clientX, y: e.clientY }; moved = false;
      svg.setPointerCapture(e.pointerId);
      e.preventDefault();
    });
    svg.addEventListener("pointermove", (e) => {
      const p = pt(e);
      if (drag && !moved && Math.hypot(e.clientX - downAt.x, e.clientY - downAt.y) < 3) return;
      if (drag) {
        moved = true;
        const m = Math.round(Math.max(Y0, Math.min(Y1, mAt(p.y))));
        clampMsg = drag === "x1" || drag === "x2"
          ? schedSetCross(this._schedPv[kind], s, drag, jAt(p.x), year)
          : schedSetVal(this._schedPv[kind], s, drag, m, kind);
        tip.hidden = true;
        changed();
        return;
      }
      const pv = this._schedPv[kind];
      if (!pv?.sun || p.x < M.l || p.x > Wd - M.r || p.y < M.t || p.y > Hd - M.b) {
        tip.hidden = true; cross?.setAttribute("visibility", "hidden"); return;
      }
      const j = jAt(p.x), r = svg.getBoundingClientRect();
      cross.setAttribute("x1", xOf(j)); cross.setAttribute("x2", xOf(j)); cross.setAttribute("visibility", "visible");
      tip.replaceChildren(el("div", "d", schedDayLabel(j, year, "long")));
      if (pv.points) tip.append(el("div", "", `${W.verb[kind]} ${hmFmt(pv.points[j - 1])} (${signedMin(pv.points[j - 1] - pv.sun[j - 1])})`));
      tip.append(el("div", "", `${W.refCap[kind]} ${hmFmt(pv.sun[j - 1])}`));
      tip.hidden = false;
      const px = xOf(j) / Wd * r.width, tw = tip.offsetWidth;
      tip.style.left = `${px + 12 + tw > r.width ? px - 12 - tw : px + 12}px`;
      tip.style.top = "40px";
    });
    svg.addEventListener("pointerup", () => { drag = null; if (clampMsg) { clampMsg = ""; redraw(); } });
    svg.addEventListener("pointerleave", () => { if (!drag) { tip.hidden = true; cross?.setAttribute("visibility", "hidden"); } });

    /* double-click on a handle: type its value, checked before it is applied */
    const NAMES = { hi: W.hi, lo: W.lo, both: W.fixedName, fl: W.fl, ce: W.ce, x1: W.x1, x2: W.x2 };
    let editor = null;
    const closeEditor = () => { editor?.remove(); editor = null; };
    svg.addEventListener("dblclick", (e) => {
      // The pointer capture makes the svg the target: take the handle of the last press.
      if (!lastKey) return;
      e.preventDefault();
      closeEditor();
      drag = null;
      const key = lastKey, isDate = key === "x1" || key === "x2";
      const value = isDate ? schedDayToIso(s[key].j, year)
        : hmFmt(key === "both" || key === "hi" ? s.hi : key === "lo" ? s.lo : s[key].m);
      editor = document.createElement("form");
      editor.className = "sched-edit";
      const label = el("label", "", NAMES[key]);
      const input = document.createElement("input");
      input.type = isDate ? "date" : "time";
      input.value = value;
      input.required = true;
      input.setAttribute("aria-label", NAMES[key]);
      const err = el("div", "err");
      err.hidden = true;
      const btns = el("div", "btns");
      const no = el("button", "btn ghost", T.cancel);
      no.type = "button";
      const ok = el("button", "btn primary", W.editApply);
      ok.type = "submit";
      btns.append(no, ok);
      editor.append(label, input, err, btns);
      chart.append(editor);
      const r = svg.getBoundingClientRect(), p = pt(e), sc = r.width / Wd;
      editor.style.left = `${Math.max(4, Math.min(p.x * sc - 100, r.width - editor.offsetWidth - 4))}px`;
      editor.style.top = `${Math.max(4, Math.min(p.y * sc + 14, r.height - editor.offsetHeight - 4))}px`;
      input.focus();
      const check = () => {
        const v = input.value;
        if (isDate) return /^\d{4}-\d{2}-\d{2}$/.test(v) && !Number.isNaN(Date.parse(v)) ? null : W.editBadDate;
        if (!/^\d{2}:\d{2}$/.test(v)) return W.editBadTime;
        const m = hmParse(v);
        return m < Y0 || m > Y1 ? W.editRange(hmFmt(Y0), hmFmt(Y1)) : null;
      };
      input.addEventListener("input", () => { input.setAttribute("aria-invalid", String(!!check())); err.hidden = true; });
      editor.addEventListener("submit", (ev) => {
        ev.preventDefault();
        const msg = check();
        if (msg) { err.textContent = msg; err.hidden = false; input.setAttribute("aria-invalid", "true"); input.focus(); return; }
        clampMsg = isDate
          ? schedSetCross(this._schedPv[kind], s, key, schedIsoToDay(input.value, year), year)
          : schedSetVal(this._schedPv[kind], s, key, hmParse(input.value), kind);
        closeEditor();
        changed();
      });
      no.addEventListener("click", closeEditor);
      editor.addEventListener("keydown", (ev) => { if (ev.key === "Escape") { ev.preventDefault(); closeEditor(); } });
    });
    // A press anywhere else closes it.
    chart.addEventListener("pointerdown", (e) => { if (editor && !e.composedPath().includes(editor)) closeEditor(); });

    redraw();
    touch();
    const resized = new ResizeObserver(() => {
      if (!chart.isConnected) { resized.disconnect(); return; }
      if (Math.round(chart.clientWidth) !== Wd && chart.clientWidth >= 560) redraw();
    });
    resized.observe(chart);
    // Both curves: the table head shows both times of the day.
    for (const k of SCHED_KINDS) {
      if (k === kind || draft.enabled[k]) this._schedRequest(k, redraw);
    }
  }

  /* ---------- RÉGLAGES (editable) ---------- */

  /** How many covers point at each facade / template. */
  _refCount(section) {
    const key = section === "facade" ? "facade" : "template";
    const out = {};
    for (const c of this._cfg.covers) {
      const name = c[key];
      if (name) out[name] = (out[name] || 0) + 1;
    }
    return out;
  }

  /**
   * The house: its facades and its templates. Lists of objects, each one
   * opening its own editor that saves on its own.
   */
  _renderHouse(wrap) {
    if (this._edit?.section === "facade") { this._facadeEditor(wrap); return; }
    if (this._edit?.section === "template") { this._templateEditor(wrap); return; }
    const cols = el("div", "house-cols");
    this._renderFacadeList(cols);
    this._renderTemplateList(cols);
    wrap.append(cols);
  }

  /**
   * The general settings: one form, one save. The generated entities come
   * last, as a check of what the configuration produced.
   */
  _renderSettings(wrap) {
    const page = el("div", "form-col");
    const stack = el("div", "ed-stack");
    const bar = this._renderGlobal(stack);
    this._renderEntities(stack);
    page.append(stack, bar);
    wrap.append(page);
  }

  _entityCounts() {
    // hass.entities is the entity registry as the frontend sees it; .platform is
    // the integration that owns the entity. Counting hass.states instead would
    // sweep in every cover this integration merely drives.
    const counts = new Map();
    for (const [eid, ent] of Object.entries(this._hass.entities)) {
      if (ent.platform !== DOMAIN) continue;
      const kind = eid.slice(0, eid.indexOf("."));
      counts.set(kind, (counts.get(kind) || 0) + 1);
    }
    return [...counts].sort((a, b) => b[1] - a[1]);
  }

  _renderEntities(wrap) {
    // No registry (a non-admin hass, an old core) is not the same as no
    // entities: say nothing rather than report a zero that would be a lie.
    if (!this._hass?.entities) return;
    const counts = this._entityCounts();
    if (!counts.length) return;

    const card = this._edCard("mdi:format-list-bulleted-type", T.entitiesSec, T.entitiesSub);
    const grid = el("div", "stats compact");
    for (const [kind, count] of counts) {
      const cell = el("div", "stat");
      const top = el("div", "stat-top");
      top.append(icon(ENTITY_ICONS[kind] || "mdi:shape-outline"),
                 el("span", "stat-n", String(count)));
      cell.append(top, el("div", "stat-k", T.entityKinds[kind] || kind));
      grid.append(cell);
    }
    card.append(grid);
    card.append(el("p", "stat-total",
      T.entityTotal(counts.reduce((total, [, count]) => total + count, 0))));
    // The counts alone told nothing about which entities they were.
    const det = document.createElement("details");
    det.className = "ents";
    const sum = document.createElement("summary");
    sum.textContent = T.entitiesShow;
    det.append(sum);
    const list = el("ul", "ent-list");
    const mine = Object.keys(this._hass.entities)
      .filter((eid) => this._hass.entities[eid].platform === DOMAIN).sort();
    for (const eid of mine) {
      const li = el("li");
      li.append(el("code", "", eid),
        el("span", "", this._hass.states[eid]?.attributes?.friendly_name || ""));
      list.append(li);
    }
    det.append(list);
    card.append(det);
    wrap.append(card);
  }

  /** A list card with an Add button in its header. */
  _listCard(iconName, title, sub, addTitle, onAdd) {
    const card = this._edCard(iconName, title, sub);
    const add = el("button", "btn");
    add.type = "button";
    add.title = addTitle;
    add.append(icon("mdi:plus"), document.createTextNode(T.addShort));
    add.addEventListener("click", onAdd);
    card.querySelector("h3").append(add);
    const list = el("div");
    card.append(list);
    return [card, list];
  }

  /** One row of a list: a round badge, a name, a line of facts, a chevron. */
  _listRow(badge, name, meta, open) {
    const row = el("button", "lrow");
    row.type = "button";
    const names = el("span");
    names.append(el("div", "nm", name), el("div", "meta", meta));
    row.append(badge, names, icon("mdi:chevron-right", "chev"));
    row.addEventListener("click", open);
    return row;
  }

  _renderFacadeList(wrap) {
    const used = this._refCount("facade");
    const [card, list] = this._listCard("mdi:compass-outline", T.facades, T.facadesSub, T.addFacade, () => {
      this._openEditor({ section: "facade", idx: -1, draft: { name: "", azimuth: 180 } });
      this._render();
    });
    this._cfg.facades.forEach((f, i) => {
      const az = facadeAzimuth(f);
      const meta = [`${az}°`, T.slopeShort(facadeTilt(f)), T.covers(used[f.name] || 0)].filter(Boolean).join(" · ");
      list.append(this._listRow(facadeArrow(f), f.name, meta, () => {
        this._openEditor({ section: "facade", idx: i, draft: { ...f } });
        this._render();
      }));
    });
    wrap.append(card);
  }

  _renderTemplateList(wrap) {
    const used = this._refCount("template");
    const [card, list] = this._listCard("mdi:ruler-square", T.templates, T.templatesSub, T.addTemplate, () => {
      const draft = { name: "" };
      for (const [name, spec] of Object.entries(this._cfg.behavior?.fields || {})) {
        if (spec.type !== "boolean") draft[name] = spec.default;
      }
      this._openEditor({ section: "template", idx: -1, draft });
      this._render();
    });
    this._cfg.templates.forEach((t, i) => {
      const badge = el("span", "round");
      badge.append(icon("mdi:ruler-square"));
      const meta = `${T.tplMeta(templateKind(t), t.shade_max_height ?? "?", t.shade_distance ?? "?")} · ${T.covers(used[t.name] || 0)}`;
      list.append(this._listRow(badge, t.name, meta, () => {
        this._openEditor({ section: "template", idx: i, draft: { ...t } });
        this._render();
      }));
    });
    wrap.append(card);
  }

  /** Who uses a facade or a template, as chips: the reason it cannot be deleted. */
  _usersChips(key, name) {
    const users = name ? this._cfg.covers.filter((c) => c[key] === name) : [];
    if (!users.length) return el("span", "ed-sub", T.noCoverYet);
    const line = el("div", "chipline");
    for (const c of users) {
      const chip = el("span", "chip");
      chip.append(icon("mdi:window-shutter"), document.createTextNode(this._coverName(c)));
      line.append(chip);
    }
    return line;
  }

  _facadeEditor(wrap) {
    const { idx, draft } = this._edit;
    const creating = idx < 0;
    const saved = creating ? null : this._cfg.facades[idx].name;
    const used = saved ? this._refCount("facade")[saved] || 0 : 0;

    wrap.append(this._backBar(T.backToFacades));

    const idCard = el("section", "card");
    const grid = el("div", "ed-ident three");
    const plate = el("div", "ed-plate");
    plate.append(icon("mdi:compass-outline"));
    grid.append(plate,
      this._labeled(T.facadeName, this._edInput(draft.name, (v) => { draft.name = v; }, "big"), "wide"),
      this._labeled(T.facadeCovers, this._usersChips("facade", saved)));
    idCard.append(grid);
    wrap.append(idCard);

    /* The compass, seen from inside: the house stays put with its facade on
       top and the arrow pointing out of the window; the rose of directions
       turns around it, like the bezel of a hand compass. Left and right on
       screen are then left and right for someone looking out, the same sides
       as the cover's "angle to the left / right". */
    const card = this._edCard("mdi:compass-rose", T.orientTitle, T.orientSub);
    card.style.marginTop = "var(--fp-s4)";
    const orient = el("div", "orient");
    const dial = el("div", "dial");
    const NS = "http://www.w3.org/2000/svg";
    const C = 120, R = 104;
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("class", "compass");
    svg.setAttribute("viewBox", "0 0 240 240");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", T.azimuth);
    const mk = (tag, attrs, parent = svg) => {
      const n = document.createElementNS(NS, tag);
      for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, String(v));
      parent.append(n);
      return n;
    };
    mk("circle", { cx: C, cy: C, r: R, fill: "var(--secondary-background-color)", stroke: "var(--divider-color)" });
    // The house, its facade and the sky in front of it: fixed, facing up.
    mk("path", { d: `M${C} ${C} L34.3 112.5 A86 86 0 0 1 205.7 112.5 Z`, fill: "var(--ce-b-shade)", "fill-opacity": ".12" });
    mk("rect", { x: 92, y: 92, width: 56, height: 56, rx: 4, fill: "var(--card-background-color)", stroke: "var(--secondary-text-color)", "stroke-opacity": ".6" });
    mk("rect", { x: 92, y: 90, width: 56, height: 5, fill: "var(--primary-color)" });
    mk("line", { x1: C, y1: 88, x2: C, y2: 64, stroke: "var(--primary-color)", "stroke-width": 3 });
    mk("path", { d: "M112 68 L120 56 L128 68 Z", fill: "var(--primary-color)" });
    mk("circle", { cx: C, cy: C, r: 3, fill: "var(--secondary-text-color)" });
    // The rose: a tick every 45°, a letter on the four cardinal points. North in red.
    const rose = T.dirs.map((label, i) => ({
      deg: i * 45,
      tick: mk("line", { stroke: "var(--secondary-text-color)", "stroke-opacity": i % 2 ? ".35" : ".7" }),
      text: i % 2 ? null : mk("text", { "text-anchor": "middle", fill: i === 0 ? "var(--fp-bad)" : "var(--secondary-text-color)" }),
      label,
    }));
    rose.forEach((r) => { if (r.text) r.text.textContent = r.label; });
    const at = (deg, r) => polar(C, C, deg, r);
    dial.append(svg);
    const sides = el("div", "compass-sides");
    const leftTxt = el("b");
    const rightTxt = el("b");
    const leftBox = el("span");
    leftBox.append(document.createTextNode(`← ${T.compassLeft} : `), leftTxt);
    const rightBox = el("span");
    rightBox.append(document.createTextNode(`${T.compassRight} : `), rightTxt, document.createTextNode(" →"));
    sides.append(leftBox, rightBox);
    dial.append(sides);

    const side = el("div");
    const azRow = el("div", "azrow");
    const box = document.createElement("input");
    box.type = "number";
    box.min = "0";
    box.max = "360";
    box.step = "1";
    box.setAttribute("aria-label", T.azimuth);
    azRow.append(box, el("span", "", "°"), el("span", "", T.dragCompass));
    const dirs = el("div", "dirs");
    const dirBtns = T.dirs.map((label, i) => {
      const b = el("button", "", label);
      b.type = "button";
      b.addEventListener("click", () => set(i * 45));
      dirs.append(b);
      return b;
    });
    side.append(el("span", "ed-lbl", T.azimuth), azRow, dirs, this._note(T.compassNote));

    const set = (deg, from) => {
      const az = wrap360(Math.round(deg));
      draft.azimuth = az;
      // A direction d sits at screen angle d - az: the azimuth itself is on top.
      for (const r of rose) {
        const a = r.deg - az;
        const [x1, y1] = at(a, R);
        const [x2, y2] = at(a, R - (r.text ? 12 : 8));
        r.tick.setAttribute("x1", x1.toFixed(1));
        r.tick.setAttribute("y1", y1.toFixed(1));
        r.tick.setAttribute("x2", x2.toFixed(1));
        r.tick.setAttribute("y2", y2.toFixed(1));
        if (r.text) {
          const [tx, ty] = at(a, R - 26);
          r.text.setAttribute("x", tx.toFixed(1));
          r.text.setAttribute("y", (ty + 5).toFixed(1));
        }
      }
      leftTxt.textContent = dirName(az - 90);
      rightTxt.textContent = dirName(az + 90);
      if (from !== box) box.value = String(az);
      dirBtns.forEach((b, i) => b.setAttribute("aria-pressed", String(az === i * 45)));
    };
    box.addEventListener("input", () => {
      if (box.value === "" || !Number.isFinite(Number(box.value))) return;
      set(Math.min(360, Math.max(0, Number(box.value))), box);
    });
    box.addEventListener("change", () => { box.value = String(draft.azimuth); });
    // Turn the rose like a bezel: it follows the pointer around the centre, so
    // turning it clockwise brings the direction on the left up to the window.
    const angleOf = (e) => {
      const r = svg.getBoundingClientRect();
      return (Math.atan2(e.clientX - (r.left + r.width / 2), -(e.clientY - (r.top + r.height / 2))) * 180) / Math.PI;
    };
    svg.addEventListener("pointerdown", (e) => {
      svg.setPointerCapture(e.pointerId);
      const start = angleOf(e);
      const from = facadeAzimuth(draft);
      const move = (ev) => set(from - (angleOf(ev) - start));
      const up = () => {
        svg.removeEventListener("pointermove", move);
        svg.removeEventListener("pointerup", up);
        svg.removeEventListener("pointercancel", up);
      };
      svg.addEventListener("pointermove", move);
      svg.addEventListener("pointerup", up);
      svg.addEventListener("pointercancel", up);
    });
    set(facadeAzimuth(draft));

    orient.append(dial, side);
    card.append(orient);
    wrap.append(card);

    /* The slope: an upright wall, a window in a roof, or a flat skylight. Shown
       in a cross-section, the window looking out to the left. */
    const slope = this._edCard("mdi:angle-acute", T.slopeTitle, T.slopeSub);
    slope.style.marginTop = "var(--fp-s4)";
    const slopeBody = el("div", "slope");
    const sketch = document.createElementNS(NS, "svg");
    sketch.setAttribute("class", "slope-sketch");
    sketch.setAttribute("viewBox", "0 0 220 120");
    sketch.setAttribute("aria-hidden", "true");
    const ctl = el("div");
    const seg = el("div", "seg");
    const presets = { wall: 90, roof: 30, flat: 0 };
    const kindBtns = {};
    for (const [k, v] of Object.entries(presets)) {
      const b = el("button", "", T.slopeKinds[k]);
      b.type = "button";
      b.addEventListener("click", () => { if (tiltKind(facadeTilt(draft)) !== k) setTilt(v); });
      seg.append(b);
      kindBtns[k] = b;
    }
    const tiltRow = el("div", "azrow");
    const tbox = document.createElement("input");
    tbox.type = "number";
    tbox.min = String(FLAT_TILT);
    tbox.max = "89";
    tbox.step = "1";
    tbox.setAttribute("aria-label", T.slopeAria);
    const trange = document.createElement("input");
    trange.type = "range";
    trange.min = String(FLAT_TILT);
    trange.max = "89";
    trange.step = "1";
    trange.tabIndex = -1;
    trange.setAttribute("aria-hidden", "true");
    tiltRow.append(tbox, el("span", "", "°"), trange);
    const slopeNote = this._note("");
    // Covers here whose template is for another type of window: saving refuses them.
    const kindWarn = this._warnNote("");
    const here = saved ? this._cfg.covers.filter((c) => c.facade === saved && this._templateOf(c)) : [];
    ctl.append(seg, tiltRow, slopeNote, kindWarn);
    slopeBody.append(sketch, ctl);
    slope.append(slopeBody);
    wrap.append(slope);

    const drawSlope = (t) => {
      sketch.replaceChildren();
      // d runs up the glass towards the room; out points out of it: up and to
      // the left for a roof, left for a wall, straight up when flat.
      const P = [96, 86], d = [Math.cos(toRad(t)), -Math.sin(toRad(t))];
      const out = [-Math.sin(toRad(t)), -Math.cos(toRad(t))];
      const f1 = (v) => v.toFixed(1);
      mk("line", { x1: f1(P[0] - d[0] * 70), y1: f1(P[1] - d[1] * 70), x2: f1(P[0] + d[0] * 70), y2: f1(P[1] + d[1] * 70),
        stroke: "var(--secondary-text-color)", "stroke-opacity": ".5", "stroke-width": 6 }, sketch);
      mk("line", { x1: f1(P[0] - d[0] * 18), y1: f1(P[1] - d[1] * 18), x2: f1(P[0] + d[0] * 18), y2: f1(P[1] + d[1] * 18),
        stroke: "var(--primary-color)", "stroke-width": 6 }, sketch);
      mk("line", { x1: P[0], y1: P[1], x2: P[0] + 60, y2: P[1], stroke: "var(--secondary-text-color)", "stroke-dasharray": "3 3" }, sketch);
      if (t > 0) {
        const r = 24, end = [P[0] + d[0] * r, P[1] + d[1] * r];
        // The angle between the horizontal and the glass.
        mk("path", { d: `M${P[0] + r} ${P[1]} A${r} ${r} 0 0 0 ${f1(end[0])} ${f1(end[1])}`, fill: "none", stroke: "var(--secondary-text-color)" }, sketch);
        const lab = mk("text", { x: P[0] + r + 6, y: P[1] - 6, fill: "var(--primary-text-color)", "font-size": "12" }, sketch);
        lab.textContent = `${t}°`;
      }
      const tip = [P[0] + out[0] * 36, P[1] + out[1] * 36];
      mk("line", { x1: P[0], y1: P[1], x2: f1(tip[0]), y2: f1(tip[1]), stroke: "var(--ce-b-shade)", "stroke-width": 2 }, sketch);
      mk("circle", { cx: f1(tip[0]), cy: f1(tip[1]), r: 4, fill: "var(--ce-b-shade)" }, sketch);
      const o = mk("text", { x: 6, y: 14, fill: "var(--secondary-text-color)", "font-size": "11" }, sketch);
      o.textContent = T.fig.outside;
      const room = mk("text", { x: 214, y: 114, fill: "var(--secondary-text-color)", "font-size": "11", "text-anchor": "end" }, sketch);
      room.textContent = T.fig.room;
    };
    // Paints without writing: opening a facade must not mark it as edited.
    const paintSlope = (t, from) => {
      const kind = tiltKind(t);
      for (const [k, b] of Object.entries(kindBtns)) {
        b.classList.toggle("on", k === kind);
        b.setAttribute("aria-pressed", String(k === kind));
      }
      tiltRow.hidden = kind !== "roof";
      if (from !== tbox) tbox.value = String(t);
      if (from !== trange) trange.value = String(t);
      slopeNote.lastChild.textContent = T.slopeNotes[kind];
      const odd = here.filter((c) => templateKind(this._templateOf(c)) !== kind);
      kindWarn.hidden = !odd.length;
      kindWarn.lastChild.textContent = T.facadeKindUsers(odd.map((c) => this._coverName(c)).join(", "));
      drawSlope(t);
    };
    const setTilt = (t, from) => {
      t = Math.max(0, Math.min(90, Math.round(t)));
      draft.tilt = t;
      paintSlope(t, from);
    };
    trange.addEventListener("input", () => setTilt(Number(trange.value), trange));
    tbox.addEventListener("input", () => {
      if (tbox.value === "" || !Number.isFinite(Number(tbox.value))) return;
      setTilt(Math.max(FLAT_TILT, Math.min(89, Number(tbox.value))), tbox);
    });
    tbox.addEventListener("change", () => { tbox.value = String(facadeTilt(draft)); });
    paintSlope(facadeTilt(draft));

    wrap.append(this._itemActions("facade", "facades", idx, draft, creating, used));
  }

  _templateEditor(wrap) {
    const { idx, draft } = this._edit;
    const creating = idx < 0;
    const saved = creating ? null : this._cfg.templates[idx].name;
    const used = saved ? this._refCount("template")[saved] || 0 : 0;
    const schema = this._cfg.behavior;

    wrap.append(this._backBar(T.backToTemplates));

    const idCard = el("section", "card");
    const grid = el("div", "ed-ident three");
    const plate = el("div", "ed-plate");
    plate.append(icon("mdi:ruler-square"));
    // The window type: switching it redraws the cards, whose sketches, words
    // and limits follow it. The draft survives the redraw.
    const kind = templateKind(draft);
    const line2 = el("div", "line2");
    const kindLbl = el("span", "ed-lbl", T.tplKind);
    kindLbl.style.margin = "0";
    const seg = el("div", "seg kind-seg");
    for (const k of ["wall", "roof", "flat"]) {
      const b = el("button", k === kind ? "on" : "", T.slopeKinds[k]);
      b.type = "button";
      b.setAttribute("aria-pressed", String(k === kind));
      b.addEventListener("click", () => {
        if (k === templateKind(draft)) return;
        if (k === "wall") delete draft.kind; else draft.kind = k;
        this._render();
      });
      seg.append(b);
    }
    line2.append(kindLbl, seg);
    grid.append(plate,
      this._labeled(T.tplName, this._edInput(draft.name, (v) => { draft.name = v; }, "big"), "wide"),
      this._labeled(T.usedBy, this._usersChips("template", saved)),
      line2);
    // Which facades this template serves, named, rather than the general rule.
    const fits = this._cfg.facades.filter((f) => tiltKind(facadeTilt(f)) === kind).map((f) => f.name);
    idCard.append(grid, this._note(fits.length ? T.tplFacades(fits.join(", ")) : T.tplNoFacade));
    const geo = this._slope(draft);
    if (kind === "roof") idCard.append(this._note(T.tplKindRef(geo.tilt, geo.refFromHouse)));
    // Covers already on it from a facade of another type: the server refuses that.
    const odd = saved ? this._cfg.covers.filter((c) => c.template === saved
      && tiltKind(facadeTilt(this._cfg.facades.find((f) => f.name === c.facade))) !== kind) : [];
    if (odd.length) idCard.append(this._warnNote(T.tplKindUsers(odd.map((c) => this._coverName(c)).join(", "))));
    wrap.append(idCard);

    if (schema) {
      const head = el("div", "ed-head");
      head.append(el("h2", "", T.calcTitle));
      // Same cards as a cover, minus the amber and the switches: passing no
      // template means _behaviorRow finds nothing to revert to.
      wrap.append(head, this._behaviorGrid(schema.template_sections || schema.sections, draft, {}, null));
    }

    wrap.append(this._itemActions("template", "templates", idx, draft, creating, used));
  }

  _backBar(label) {
    const bar = el("div", "toolbar");
    const back = el("button", "btn ghost");
    back.append(icon("mdi:arrow-left"), document.createTextNode(label));
    back.addEventListener("click", () => { if (this._leaveEditor()) this._render(); });
    bar.append(back);
    return bar;
  }

  /** Delete / cancel / save for a named item of *section*, stored in cfg[key]. */
  _itemActions(section, key, idx, draft, creating, used) {
    return this._saveBar(() => {
      const items = this._cfg[key].map((it) => ({ ...it }));
      if (creating) items.push(draft); else items[idx] = draft;
      this._saveSection(section, items);
    }, creating ? null : {
      used, reason: T.inUseItemTitle(used),
      onDelete: () => this._saveSection(section, this._cfg[key].filter((_, i) => i !== idx).map((it) => ({ ...it }))),
    });
  }

  /**
   * The solar-gain threshold: a number typed here, or an entity (an
   * input_number) to change it from a dashboard. The server takes either; left
   * empty, it uses 19. Each side remembers its value while the other is shown,
   * so trying the other one and coming back loses nothing.
   */
  _thresholdControl(draft, touch) {
    const raw = draft.sg_temperature_threshold;
    const isEntity = typeof raw === "string" && raw.includes(".");
    let lastEntity = isEntity ? raw : undefined;
    let lastValue = isEntity || raw == null || raw === "" ? undefined : Number(raw);
    const unit = this._hass.states[draft.sg_temperature_entity]?.attributes?.unit_of_measurement || "°C";
    const box = el("div", "thr");
    const seg = el("div", "seg thr-seg");
    const byValue = el("button", "", T.sgThrValue);
    const byEntity = el("button", "", T.sgThrEntity);
    for (const b of [byValue, byEntity]) b.type = "button";
    seg.append(byValue, byEntity);
    const body = el("div", "thr-body");
    box.append(seg, body);
    const show = (entity) => {
      byValue.classList.toggle("on", !entity);
      byEntity.classList.toggle("on", entity);
      byValue.setAttribute("aria-pressed", String(!entity));
      byEntity.setAttribute("aria-pressed", String(entity));
      if (entity) {
        body.replaceChildren(this._haSelector({ entity: { domain: ["input_number", "number"] } }, lastEntity, (v) => {
          lastEntity = v || undefined;
          draft.sg_temperature_threshold = lastEntity;
          touch();
        }));
        this._trackLiveNodes();
        return;
      }
      const n = document.createElement("input");
      n.type = "number";
      n.step = "0.5";
      n.min = "-30";
      n.max = "50";
      n.value = String(lastValue ?? 19);
      n.setAttribute("aria-label", T.sgThreshold);
      n.addEventListener("input", () => {
        // An empty box is a transient state while typing, not a zero.
        if (n.value === "" || !Number.isFinite(Number(n.value))) return;
        lastValue = Number(n.value);
        draft.sg_temperature_threshold = lastValue;
        touch();
      });
      body.replaceChildren(n, el("span", "u", unit));
    };
    byValue.addEventListener("click", () => { draft.sg_temperature_threshold = lastValue; show(false); touch(); });
    byEntity.addEventListener("click", () => { draft.sg_temperature_threshold = lastEntity; show(true); touch(); });
    show(isEntity);
    return box;
  }

  /** "21.4 °C ≥ 18": where the temperature stands against the threshold right now. */
  _solarGainVerdict(draft) {
    const st = this._hass.states;
    const temp = st[draft.sg_temperature_entity];
    const t = parseFloat(temp?.state);
    const raw = draft.sg_temperature_threshold;
    const s = st[raw] ? parseFloat(st[raw].state) : parseFloat(raw);
    if (!Number.isFinite(t) || !Number.isFinite(s)) return null;
    const unit = temp.attributes?.unit_of_measurement;
    const shown = `${t}${unit ? ` ${unit}` : ""}`;
    const warm = t >= s;
    const chip = el("span", `chip verdict ${warm ? "inhib" : "ok"}`);
    chip.append(icon(warm ? "mdi:pause" : "mdi:check"),
      document.createTextNode(warm ? T.sgTooWarm(shown, s) : T.sgCool(shown, s)));
    return chip;
  }

  /**
   * General settings. A single item, so it is edited in place: the draft lives on
   * the instance, not in _edit, and survives the re-renders a selector triggers.
   * Returns its save bar, for the caller to place under the whole page.
   */
  _renderGlobal(wrap) {
    const draft = this._globalDraft || (this._globalDraft = { ...(this._cfg.global || {}) });
    // Pristine copy for the unsaved-changes guard: these settings are edited in
    // place, so there is no editor object to hang a snapshot off.
    if (this._globalClean === null) this._globalClean = JSON.stringify(draft);
    const conditions = this._cfg.weather_conditions || [];
    const interval = this._cfg.defaults?.command_interval ?? 150;

    const bar = this._saveBar(() => { this._saveSection("global", { ...draft }); });
    const touch = () => this._syncSaveBar?.();

    /* solar gain: when is it cool and fine enough, written as the rule reads */
    const sg = this._edCard("mdi:thermometer", T.sgTitle, T.sgSub);
    const cool = el("div", "sentence sg-line");
    cool.append(el("span", "", T.sgCoolWhen), this._haSelector(
      { entity: { domain: "sensor", device_class: "temperature" } },
      draft.sg_temperature_entity || undefined,
      (v) => { draft.sg_temperature_entity = v || undefined; touch(); }),
    el("span", "", T.sgIsBelow), this._thresholdControl(draft, touch));
    sg.append(cool);
    const verdict = this._solarGainVerdict(draft);
    if (verdict) sg.append(verdict);
    const fine = el("div", "sentence sg-line");
    fine.append(el("span", "", T.sgFineWhen), this._haSelector({ entity: { domain: "weather" } },
      draft.sg_weather_entity || undefined,
      (v) => { draft.sg_weather_entity = v || undefined; touch(); }), el("span", "", T.sgReports));
    sg.append(fine);
    // The chosen conditions first; the others fold behind "+ n more". The
    // order is taken once, so a chip does not jump away when it is clicked.
    const wx = el("div", "toggles wx-list");
    const good = () => draft.sg_good_conditions ?? ["sunny", "partlycloudy"];
    const picked = new Set(good());
    const ordered = [...conditions.filter((c) => picked.has(c)), ...conditions.filter((c) => !picked.has(c))];
    const extras = [];
    for (const c of ordered) {
      const b = el("button", "toggle wx");
      b.type = "button";
      b.append(icon(WEATHER_ICONS[c] || "mdi:weather-cloudy"), document.createTextNode(T.weatherStates[c] || c));
      const sync = () => b.setAttribute("aria-pressed", String(good().includes(c)));
      sync();
      b.addEventListener("click", () => {
        const now = good();
        draft.sg_good_conditions = now.includes(c) ? now.filter((x) => x !== c) : [...now, c];
        sync();
        touch();
      });
      if (!picked.has(c)) extras.push(b);
      wx.append(b);
    }
    if (extras.length) {
      const more = el("button", "toggle more");
      more.type = "button";
      const fold = (open) => {
        this._wxOpen = open;
        for (const b of extras) b.hidden = !open;
        more.textContent = open ? T.sgLess : T.sgMore(extras.length);
      };
      more.addEventListener("click", () => fold(!this._wxOpen));
      wx.append(more);
      fold(!!this._wxOpen);
    }
    sg.append(wx, this._note(T.sgNote));

    /* sending commands */
    const cmd = this._edCard("mdi:send-clock-outline", T.cmdTitle);
    const row = el("div", "numf");
    row.append(el("div", "t", T.interval), el("div", "h", T.intervalHint));
    const ms = document.createElement("input");
    ms.type = "number";
    ms.min = "0";
    ms.max = "5000";
    ms.step = "10";
    ms.value = String(draft.command_interval ?? interval);
    ms.setAttribute("aria-label", T.interval);
    ms.addEventListener("input", () => {
      // An empty box is a transient state while typing, not a zero.
      if (ms.value !== "") { draft.command_interval = Number(ms.value); touch(); }
    });
    const val = el("div", "val");
    val.append(ms, el("span", "u", "ms"));
    row.append(val);
    cmd.append(row);

    /* the optional per-cover entities */
    const extra = this._edCard("mdi:plus-box-multiple-outline", T.extraTitle, T.extraSub);
    extra.append(
      this._optRow("mdi:sun-angle-outline", T.showSunFacing, T.showHints.sun_facing,
        draft.show_sun_facing ?? true, (v) => { draft.show_sun_facing = v; touch(); }),
      this._optRow("mdi:weather-sunny", T.showAutoShade, T.showHints.auto_shade,
        draft.show_auto_shade ?? true, (v) => { draft.show_auto_shade = v; touch(); }),
      this._optRow("mdi:thermometer", T.showSolarGain, T.showHints.solar_gain,
        draft.show_solar_gain ?? false, (v) => { draft.show_solar_gain = v; touch(); }));

    wrap.append(sg, cmd, extra);
    return bar;
  }
}

customElements.define("cover-extender-panel", CoverExtenderPanel);
