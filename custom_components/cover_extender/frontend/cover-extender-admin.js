/**
 * Cover Extender — admin panel.
 *
 * A custom panel reached from the sidebar, from the hub device's
 * configuration_url, or at /cover-extender directly. It is the only way to
 * configure the integration: the config flow creates the entry and stops there.
 *
 * Four tabs, all editable: Covers, Matrix (modes × covers, the screen a config
 * flow cannot draw), Modes, Settings — facades, templates, the global settings
 * and a read-only count of what all this produced in Home Assistant.
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
    tabs: { matrice: "Matrix", volets: "Covers", modes: "Modes", horaires: "Schedules", reglages: "Settings" },
    sched: {
      intro: "At the morning and evening times, Cover Extender applies to each cover the mode chosen below. It is a mode change like any other: exclusions, inhibitions, lock and timed modes apply.",
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
      refWord: "reference",
      band: { morning: "Open before sunrise", evening: "Closed before sunset" },
      hi: "Max time", hiFixed: "Max time = min", lo: "Min time",
      x1: "Spring crossing", x2: "Autumn crossing",
      fl: "Floor · not before", ce: "Ceiling · not after", flShort: "floor", ceShort: "ceiling",
      fixedHint: "For a fixed time all year round, drag the max and min handles together until they stick.",
      dstHint: (h) => ` Here they are either together or at least ${h} h apart, because of daylight saving time.`,
      legal: "legal time", off: "off", offHalf: "off · plain half-sine",
      unusedFixed: "unused with a fixed time", glued: "stuck to max: fixed time",
      fixedAll: "fixed time all year, legal time", ignoredShort: " · ignored",
      fixedLabel: (t) => `fixed time ${t}`,
      fixedName: "Fixed time",
      dblHint: " Double-click a handle to type its value.",
      editApply: "Apply",
      editBadTime: "Invalid time: type HH:MM.",
      editRange: (a, b) => `Choose a time between ${a} and ${b}.`,
      editBadDate: "Invalid date: type day, month and year.",
      today: "Today", earliest: "Earliest", latest: "Latest",
      maxAfter: (r) => `Largest gap after ${r}`, daysBefore: (r) => `Days before ${r}`,
      onDate: (d) => `on ${d}`, none: "none", upTo: (n, d) => `up to ${n}, on ${d}`,
      errors: {
        schedule_min_after_max: "The min time is after the max time. For a fixed time, enter the same time in both fields.",
        schedule_floor_after_ceiling: "The floor is not before the ceiling.",
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
      clampHiFl: (t) => `The max cannot go below the floor (${t}).`,
      clampLoHi: "The min cannot go above the max: the handles stay together.",
      clampLoCe: (t) => `The min cannot go above the ceiling (${t}).`,
      clampFlHi: (t) => `The floor cannot go above the max (${t}).`,
      clampFlCe: (t) => `The floor stays below the ceiling (${t}).`,
      clampCeLo: (t) => `The ceiling cannot go below the min (${t}).`,
      clampCeFl: (t) => `The ceiling stays above the floor (${t}).`,
      clampGap: "A curve needs at least 1 h between max and min: below that, the clock change would push it under the min in winter.",
      clampCross: (k, a, b) => `The ${k.toLowerCase()} stays between ${a} and ${b}.`,
      perCover: "Mode applied per cover",
      perCoverSub: "“None”: the cover does not follow this schedule. Only the modes linked to the cover and without a duration are offered.",
      cover: "Cover", noneOpt: "None",
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
    legendEmpty: "Not linked",
    auto: "auto",
    linkMode: "Link this mode",
    matrixHint: "Click a cell to set the mode's position on that cover; an empty cell links the mode.",
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
    segAuto: "Auto",
    noneHint: "No position forced: the cover stays where it is (locked if the mode locks).",
    entityHint: "The entity's value drives the position live.",
    autoHint: "Default: the position is computed for this cover.",
    overrideHint: "Override: this cover ignores the computed position while in this mode.",
    overrideTitle: "Overrides the computed position",
    applyFacade: (n, f) => `Apply to the ${n} other covers on the ${f} facade too`,
    applyFacadeOne: (f) => `Apply to the other cover on the ${f} facade too`,
    unlink: "Unlink",
    link: "Link",
    cancel: "Cancel",
    save: "Save",
    saved: "Saved — configuration reloaded",
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
    active: "on",
    // French agrees the adjective with the noun; English has one word for both.
    activeF: "on",
    lock: "lock",
    hidden: "hidden",
    facades: "Facades",
    templates: "Templates",
    globalSettings: "General settings",
    tempEntity: "Temperature entity",
    threshold: "Threshold entity",
    weather: "Weather entity",
    interval: "Interval between commands",
    facadesSub: "The azimuth is the way the facade faces: 0° = north, 90° = east.",
    templatesSub: "Base values inherited by the covers; each one may depart from them.",
    globalSub: "Entities and settings shared by the whole integration.",
    addFacade: "Add a facade",
    addTemplate: "Add a template",
    newFacade: "New facade",
    newTemplate: "New template",
    backToFacades: "All facades",
    backToTemplates: "All templates",
    templateTitle: "Template",
    azimuth: "Azimuth",
    goodConditions: "Good weather conditions",
    goodConditionsHint: "Weather states that allow solar gain.",
    intervalHint: "Delay between two commands sent to the covers, in milliseconds.",
    display: "Display",
    showSunFacing: "“Sun facing” sensor",
    showAutoShade: "“Automatic shading” sensor",
    showSolarGain: "“Solar gain” sensor",
    tplNoOverrideNote: "A template is the reference: its values have no override to show.",
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
    dragHint: "Drag a tile to reorder — the order drives the mode selector's list.",
    backToModes: "All modes",
    newMode: "New mode",
    mode: "Mode",
    name: "Name",
    icon: "Icon",
    color: "Color",
    behavior: "Behavior",
    behaviorNone: "None — fixed position per cover",
    behaviorHint: "Positions are computed; the matrix can still override them cover by cover (fixed or entity).",
    lockField: "Lock the covers",
    lockHint: "Commands sent through Cover Extender are memorized instead of moving the cover while the mode is on.",
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
    inUseTitle: (n) => `Used by ${n} cover(s) — unlink it in the matrix first.`,
    inUseItemTitle: (n) => `Used by ${n} cover(s) — reassign them first.`,
    newCover: "New cover",
    backToCovers: "All covers",
    entity: "Cover entity",
    picture: "Picture",
    exclusion: "Safety exclusions",
    exclusionHint: "While one of these entities is on, nothing moves, not even a priority mode. What was asked meanwhile is applied once they turn off. E.g. an open window, a rain sensor.",
    inhibition: "Inhibitions",
    inhibitionHint: "While one of these entities is on, Cover Extender leaves the cover alone, except for a priority mode. What was asked meanwhile is applied once they turn off. E.g. a guest, children, a template sensor for “Wednesday morning”.",
    priorityField: "Priority mode",
    priorityHint: "Passes the inhibitions, never the safety exclusions. Same as the apply_mode action with force: true.",
    priority: "priority",
    durationField: "Timed mode",
    durationHint: "When the time is up, the cover leaves this mode on its own. Choosing a mode without a duration before that ends it at once.",
    durationLabel: "Duration",
    returnField: "When the time is up",
    returnBase: "Back to the base mode",
    returnHint: "The base mode is the last mode without a duration the cover was in. Only modes without a duration can be chosen here.",
    timedChip: (n, r) => (r ? `${n} min, then ${r}` : `${n} min`),
    statusTimer: (m, t) => `back to ${m} at ${t}`,
    statusLocked: (p) => (p == null ? "locked" : `locked, ${p} % remembered`),
    entitiesShow: "Show the entities",
    usedAsReturn: (names) => `This mode is the one ${names.map((n) => `“${n}”`).join(", ")} returns to: it cannot have a duration while it is.`,
    noTemplateOpt: "No template",
    overrides: (n) => `${n} override${n > 1 ? "s" : ""}`,
    tplNote: (n) => `Values inherited from the “${n}” template: only the overrides are stored.`,
    noTplNote: "No template: every value belongs to this cover alone.",
    revertTitle: "Back to the template's value",
    sections: { geometry: "Geometry", detection: "Detection", shading: "Shading", solar_gain: "Solar gain" },
    fields: {
      angle_left: "Angle to the left", angle_right: "Angle to the right",
      shade_distance: "Distance from the cover", shade_max_height: "Maximum height",
      shade_min_height: "Minimum height", shade_degrees: "Angular aperture",
      shade_min_elevation: "Minimum elevation", shade_max_elevation: "Maximum elevation",
      shade_minimum_position: "Minimum position", shade_default_position: "Default position",
      shade_change_threshold: "Change threshold", shade_time_out: "Time-out",
      solar_gain_position_solar: "Position in the sun", solar_gain_position_cold: "Position when cold",
      shade_enable: "Automatic shading enabled", solar_gain_enable: "Solar gain enabled",
    },
    errors: {
      name_required: () => "The name cannot be empty.",
      name_exists: (n) => `The name “${n}” is already taken.`,
      behavior_invalid: (n) => `Invalid behavior for “${n}”.`,
      color_invalid: (n) => `Invalid color for “${n}”.`,
      duration_invalid: (n) => `Duration of “${n}”: between 1 and 1440 minutes.`,
      return_mode_invalid: (n) => `“${n}”: the mode it returns to must be an existing mode without a duration.`,
      schedule_mode_timed: (m) => `“${m}” is applied by a schedule: it cannot have a duration, and a mode with a duration cannot be scheduled.`,
      schedule_invalid: (k) => `The ${k} schedule cannot be read.`,
      schedule_min_after_max: (k) => `The ${k} schedule: the min time is after the max time.`,
      schedule_floor_after_ceiling: (k) => `The ${k} schedule: the floor is not before the ceiling.`,
      return_mode_timed: (target, user) => `“${target}” is the mode “${user}” returns to: it cannot have a duration. Change the return of “${user}” first.`,
      in_use: (n, count, covers) => `“${n}” is still used by ${count} cover(s): ${covers}`,
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
      field_invalid: (f) => `Unreadable value for “${f}”.`,
      interval_invalid: () => "The interval must be between 0 and 5000 ms.",
      conditions_invalid: () => "Unreadable list of weather conditions.",
      condition_unknown: (c) => `Unknown weather condition: ${c}`,
    },
  },

  fr: {
    tabs: { matrice: "Matrice", volets: "Volets", modes: "Modes", horaires: "Horaires", reglages: "Réglages" },
    sched: {
      intro: "À l'heure du matin et du soir, Cover Extender applique à chaque volet le mode choisi plus bas. C'est un changement de mode comme un autre : les exclusions, les inhibitions, le verrou et les modes minutés s'appliquent.",
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
      refWord: "référence",
      band: { morning: "Ouvert avant le lever", evening: "Fermé avant le coucher" },
      hi: "Heure max", hiFixed: "Heure max = min", lo: "Heure min",
      x1: "Croisement printemps", x2: "Croisement automne",
      fl: "Plancher · pas avant", ce: "Plafond · pas après", flShort: "plancher", ceShort: "plafond",
      fixedHint: "Pour une heure fixe toute l'année, rapproche les poignées max et min jusqu'à ce qu'elles se collent.",
      dstHint: (h) => ` Ici, elles sont soit collées, soit écartées d'au moins ${h} h, à cause de l'heure d'été.`,
      legal: "heure légale", off: "désactivé", offHalf: "désactivé · demi-sinusoïde simple",
      unusedFixed: "inutilisé en heure fixe", glued: "collée au max : heure fixe",
      fixedAll: "heure fixe toute l'année, heure légale", ignoredShort: " · ignoré",
      fixedLabel: (t) => `heure fixe ${t}`,
      fixedName: "Heure fixe",
      dblHint: " Double-clic sur une poignée pour taper sa valeur.",
      editApply: "Appliquer",
      editBadTime: "Heure invalide : saisis HH:MM.",
      editRange: (a, b) => `Choisis une heure entre ${a} et ${b}.`,
      editBadDate: "Date invalide : saisis jour, mois et année.",
      today: "Aujourd'hui", earliest: "Le plus tôt", latest: "Le plus tard",
      maxAfter: (r) => `Plus grand écart après le ${r}`, daysBefore: (r) => `Jours avant le ${r}`,
      onDate: (d) => `le ${d}`, none: "aucun", upTo: (n, d) => `jusqu'à ${n}, le ${d}`,
      errors: {
        schedule_min_after_max: "L'heure min est après l'heure max. Pour une heure fixe, mets la même heure dans les deux champs.",
        schedule_floor_after_ceiling: "Le plancher n'est pas avant le plafond.",
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
      clampHiFl: (t) => `Le max ne descend pas sous le plancher (${t}).`,
      clampLoHi: "Le min ne monte pas au-dessus du max : les poignées restent collées.",
      clampLoCe: (t) => `Le min ne monte pas au-dessus du plafond (${t}).`,
      clampFlHi: (t) => `Le plancher ne monte pas au-dessus du max (${t}).`,
      clampFlCe: (t) => `Le plancher reste sous le plafond (${t}).`,
      clampCeLo: (t) => `Le plafond ne descend pas sous le min (${t}).`,
      clampCeFl: (t) => `Le plafond reste au-dessus du plancher (${t}).`,
      clampGap: "Entre l'heure fixe et la courbe, il faut au moins 1 h d'écart : en dessous, le changement d'heure ferait passer la courbe sous le min en hiver.",
      clampCross: (k, a, b) => `Le ${k.toLowerCase()} reste entre le ${a} et le ${b}.`,
      perCover: "Mode appliqué par volet",
      perCoverSub: "« Aucun » : le volet ne suit pas cet horaire. Seuls les modes liés au volet et sans durée sont proposés.",
      cover: "Volet", noneOpt: "Aucun",
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
    legendEmpty: "Non lié",
    auto: "auto",
    linkMode: "Lier ce mode",
    matrixHint: "Cliquer une cellule pour régler la position du mode sur ce volet ; une cellule vide lie le mode.",
    posSub: "Position appliquée quand ce mode est activé",
    behaviorSub: {
      auto_shade: "Position calculée par l'ombrage automatique",
      solar_gain: "Position calculée par l'héliotropie",
    },
    segFixed: "Fixe",
    segEntity: "Entité",
    segNone: "Aucune",
    segAuto: "Auto",
    noneHint: "Pas de position forcée : le volet reste en place (verrouille si mode verrou).",
    entityHint: "La valeur de l'entité pilote la position en direct.",
    autoHint: "Par défaut : la position est calculée pour ce volet.",
    overrideHint: "Surcharge : ce volet ignore la position calculée dans ce mode.",
    overrideTitle: "Surcharge la position calculée",
    applyFacade: (n, f) => `Appliquer aussi aux ${n} autres volets de la façade ${f}`,
    applyFacadeOne: (f) => `Appliquer aussi à l'autre volet de la façade ${f}`,
    unlink: "Délier",
    link: "Lier",
    cancel: "Annuler",
    save: "Enregistrer",
    saved: "Enregistré — configuration rechargée",
    saveError: "Échec de l'enregistrement",
    rawError: (raw) => `Échec de l'enregistrement : ${raw}`,
    discardConfirm: "Des modifications ne sont pas enregistrées. Les abandonner ?",
    saving: "Enregistrement…",
    covers: (n) => `${n} volet${n > 1 ? "s" : ""}`,
    modesCount: (n) => `${n} mode${n > 1 ? "s" : ""}`,
    shading: "Ombrage",
    solarGain: "Héliotropie",
    active: "actif",
    activeF: "active",
    lock: "verrou",
    hidden: "masqué",
    facades: "Façades",
    templates: "Gabarits",
    globalSettings: "Réglages globaux",
    tempEntity: "Entité de température",
    threshold: "Entité de seuil",
    weather: "Entité météo",
    interval: "Intervalle entre commandes",
    facadesSub: "L'azimut est l'orientation de la façade : 0° = nord, 90° = est.",
    templatesSub: "Valeurs de base héritées par les volets ; chacun peut s'en écarter.",
    globalSub: "Entités et réglages communs à toute l'intégration.",
    addFacade: "Ajouter une façade",
    addTemplate: "Ajouter un gabarit",
    newFacade: "Nouvelle façade",
    newTemplate: "Nouveau gabarit",
    backToFacades: "Toutes les façades",
    backToTemplates: "Tous les gabarits",
    templateTitle: "Gabarit",
    azimuth: "Azimut",
    goodConditions: "Bonnes conditions météo",
    goodConditionsHint: "États du service météo qui autorisent l'apport solaire.",
    intervalHint: "Délai entre deux commandes envoyées aux volets, en millisecondes.",
    display: "Affichage",
    showSunFacing: "Capteur « face au soleil »",
    showAutoShade: "Capteur « ombrage automatique »",
    showSolarGain: "Capteur « héliotropie »",
    tplNoOverrideNote: "Un gabarit est la référence : ses valeurs n'ont pas d'écart à afficher.",
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
    dragHint: "Glisser une tuile pour réordonner — l'ordre pilote la liste du sélecteur de mode.",
    backToModes: "Tous les modes",
    newMode: "Nouveau mode",
    mode: "Mode",
    name: "Nom",
    icon: "Icône",
    color: "Couleur",
    behavior: "Comportement",
    behaviorNone: "Aucun — position fixe par volet",
    behaviorHint: "Les positions sont calculées ; la matrice peut les surcharger volet par volet (fixe ou entité).",
    lockField: "Verrouiller les volets",
    lockHint: "Les commandes passées par Cover Extender sont mémorisées au lieu de bouger le volet tant que le mode est actif.",
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
    inUseTitle: (n) => `Utilisé par ${n} volet(s) — délier d'abord dans la matrice.`,
    inUseItemTitle: (n) => `Utilisé par ${n} volet(s) — les réaffecter d'abord.`,
    newCover: "Nouveau volet",
    backToCovers: "Tous les volets",
    entity: "Entité du volet",
    picture: "Image",
    exclusion: "Exclusions de sécurité",
    exclusionHint: "Tant qu'une de ces entités est allumée, rien ne bouge, même un mode prioritaire. Ce qui a été demandé entre-temps s'applique quand elles retombent. Ex. : une fenêtre ouverte, un capteur de pluie.",
    inhibition: "Inhibitions",
    inhibitionHint: "Tant qu'une de ces entités est allumée, Cover Extender ne touche pas au volet, sauf pour un mode prioritaire. Ce qui a été demandé entre-temps s'applique quand elles retombent. Ex. : un invité, les enfants, un capteur template « mercredi matin ».",
    priorityField: "Mode prioritaire",
    priorityHint: "Passe outre les inhibitions, jamais les exclusions de sécurité. Comme l'action apply_mode avec force: true.",
    priority: "prioritaire",
    durationField: "Mode minuté",
    durationHint: "À la fin du délai, le volet quitte ce mode tout seul. Choisir un mode sans durée avant y met fin tout de suite.",
    durationLabel: "Durée",
    returnField: "À la fin du délai",
    returnBase: "Revenir au mode de base",
    returnHint: "Le mode de base est le dernier mode sans durée dans lequel était le volet. Seuls les modes sans durée peuvent être choisis ici.",
    timedChip: (n, r) => (r ? `${n} min, puis ${r}` : `${n} min`),
    statusTimer: (m, t) => `retour à ${m} à ${t}`,
    statusLocked: (p) => (p == null ? "verrouillé" : `verrouillé, ${p} % mémorisé`),
    entitiesShow: "Voir les entités",
    usedAsReturn: (names) => `Ce mode est le mode de retour de ${names.map((n) => `« ${n} »`).join(", ")} : il ne peut pas avoir de durée tant qu'il l'est.`,
    noTemplateOpt: "Aucun gabarit",
    overrides: (n) => `${n} écart${n > 1 ? "s" : ""}`,
    tplNote: (n) => `Valeurs héritées du gabarit « ${n} » : seuls les écarts sont enregistrés.`,
    noTplNote: "Sans gabarit : toutes les valeurs sont propres à ce volet.",
    revertTitle: "Revenir à la valeur du gabarit",
    sections: { geometry: "Géométrie", detection: "Détection", shading: "Ombrage", solar_gain: "Héliotropie" },
    fields: {
      angle_left: "Angle à gauche", angle_right: "Angle à droite",
      shade_distance: "Distance du volet", shade_max_height: "Hauteur maxi",
      shade_min_height: "Hauteur mini", shade_degrees: "Ouverture angulaire",
      shade_min_elevation: "Élévation mini", shade_max_elevation: "Élévation maxi",
      shade_minimum_position: "Position mini", shade_default_position: "Position par défaut",
      shade_change_threshold: "Seuil de changement", shade_time_out: "Temporisation",
      solar_gain_position_solar: "Position au soleil", solar_gain_position_cold: "Position au froid",
      shade_enable: "Ombrage automatique activé", solar_gain_enable: "Héliotropie activée",
    },
    errors: {
      name_required: () => "Le nom ne peut pas être vide.",
      name_exists: (n) => `Le nom « ${n} » existe déjà.`,
      behavior_invalid: (n) => `Comportement invalide pour « ${n} ».`,
      color_invalid: (n) => `Couleur invalide pour « ${n} ».`,
      duration_invalid: (n) => `Durée de « ${n} » : entre 1 et 1440 minutes.`,
      return_mode_invalid: (n) => `« ${n} » : le mode de retour doit être un mode existant sans durée.`,
      schedule_mode_timed: (m) => `« ${m} » est appliqué par un horaire : il ne peut pas avoir de durée, et un mode avec une durée ne peut pas être programmé.`,
      schedule_invalid: (k) => `L'horaire « ${k} » est illisible.`,
      schedule_min_after_max: (k) => `Horaire « ${k} » : l'heure min est après l'heure max.`,
      schedule_floor_after_ceiling: (k) => `Horaire « ${k} » : le plancher n'est pas avant le plafond.`,
      return_mode_timed: (target, user) => `« ${target} » est le mode de retour de « ${user} » : il ne peut pas avoir de durée. Changez d'abord le retour de « ${user} ».`,
      in_use: (n, count, covers) => `« ${n} » est encore utilisé par ${count} volet(s) : ${covers}`,
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
    // Plain objects merge; strings and functions replace. `typeof fn` is
    // "function", never "object", so a translated function is never walked into.
    out[key] =
      value && typeof value === "object" && under && typeof under === "object"
        ? mergeWords(under, value)
        : value;
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

/* ---------- colour + error helpers ---------- */
function hexToRgb(hex) {
  const h = String(hex || "#FFFFFF").replace("#", "");
  if (h.length !== 6) return [255, 255, 255];
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
}

function rgbToHex(rgb) {
  if (!Array.isArray(rgb) || rgb.length < 3) return "#FFFFFF";
  return `#${rgb.slice(0, 3)
    .map((n) => Math.max(0, Math.min(255, Number(n) | 0)).toString(16).padStart(2, "0"))
    .join("")}`.toUpperCase();
}

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
  .m-tools { display: flex; align-items: center; gap: var(--fp-s4); flex-wrap: wrap; margin: 0 0 var(--fp-s3); }
  .legend { display: flex; gap: var(--fp-s4); margin-left: auto; font-size: var(--f-12);
            color: var(--secondary-text-color); flex-wrap: wrap; }
  .legend span { display: inline-flex; align-items: center; gap: var(--fp-sh); }
  .legend ha-icon { --mdc-icon-size: 15px; width: 15px; height: 15px; }
  .lg { width: 22px; height: 15px; border-radius: var(--fp-field-r); display: inline-block; }
  .lg.fixed { background: var(--secondary-background-color); border: 1px solid var(--divider-color); }
  .lg.empty { border: 1px dashed var(--divider-color); }

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
  .mh { display: flex; flex-direction: column; align-items: center; gap: var(--fp-s1);
        padding: var(--fp-s3) var(--fp-s2) var(--fp-sh);
        min-width: 76px; font-weight: 500; font-size: var(--f-11-5); color: var(--secondary-text-color); }
  .mh .mico { width: 27px; height: 27px; border-radius: var(--fp-ctl-r);
              display: flex; align-items: center; justify-content: center; }
  .mh .mico ha-icon { --mdc-icon-size: 16px; width: 16px; height: 16px; }
  .mh .flags { display: flex; gap: var(--fp-s1); min-height: 13px; }
  .mh .flags ha-icon { --mdc-icon-size: 12px; width: 12px; height: 12px; color: var(--secondary-text-color); }
  .rowh { display: flex; align-items: center; gap: var(--fp-s3);
          padding: var(--fp-sh) var(--fp-s4) var(--fp-sh) var(--fp-s3); min-width: 200px; }
  .rowh img, .rowh .pic { width: var(--fp-pill-h); height: var(--fp-pill-h);
                          border-radius: var(--fp-ctl-r); object-fit: cover; flex: none; }
  .rowh .pic { background: var(--secondary-background-color); border: 1px solid var(--divider-color);
               display: flex; align-items: center; justify-content: center; color: var(--secondary-text-color); }
  .rowh .pic ha-icon { --mdc-icon-size: 16px; width: 16px; height: 16px; }
  .rowh .nm { font-weight: 600; font-size: var(--f-13); line-height: 1.25; }
  .rowh .fx { font-size: var(--f-11); color: var(--secondary-text-color); }
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
  .cv.empty { border: 1px dashed var(--divider-color); color: transparent; }
  .cv.empty:hover { color: var(--secondary-text-color); border-color: var(--secondary-text-color); }
  .cv.empty ha-icon { --mdc-icon-size: 14px; width: 14px; height: 14px; }
  .gauge { width: 26px; height: 5px; border-radius: var(--fp-field-r); background: var(--divider-color);
           overflow: hidden; flex: none; }
  .gauge i { display: block; height: 100%; background: var(--primary-color); }
  .pct { color: var(--secondary-text-color); font-weight: 500; font-size: var(--f-10-5); }

  /* ---------- popover ---------- */
  .backdrop { position: fixed; inset: 0; z-index: 8; }
  /* Fixed, not absolute: the popover lives OUTSIDE .m-scroll so it is never
     clipped by it and never grows its scroll area. Re-anchored on scroll. */
  .pop { position: fixed; z-index: 9; width: 290px; max-width: calc(100vw - 16px);
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
  .pos-slider input[type=range] { flex: 1; accent-color: var(--primary-color); }
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
  .btn[disabled] { opacity: .5; cursor: default; }
  ha-selector { display: block; margin-bottom: var(--fp-s3); }

  /* ---------- read-only tabs ---------- */
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(290px, 1fr)); gap: var(--fp-s3); }
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
  .feats { display: flex; gap: var(--fp-s4); font-size: var(--f-12-5); color: var(--secondary-text-color);
           border-top: 1px solid var(--divider-color); padding-top: var(--fp-s2); }
  .feats ha-icon { --mdc-icon-size: 15px; width: 15px; height: 15px; }
  .feats .on { color: var(--fp-ok); font-weight: 600; }
  /* Mode tiles reuse the cover-card anatomy: .card > .c-head + .chips. */
  .mico { width: 38px; height: 38px; border-radius: var(--fp-ctl-r); flex: none;
          display: flex; align-items: center; justify-content: center; }
  .mico ha-icon { --mdc-icon-size: 20px; width: 20px; height: 20px; }
  .m-ord { flex: none; min-width: 22px; height: 22px; padding: 0 var(--fp-s0); display: flex;
           align-items: center; justify-content: center; border-radius: var(--fp-pill-r);
           background: var(--secondary-background-color); color: var(--secondary-text-color);
           font-size: var(--f-11); font-weight: 700; font-variant-numeric: tabular-nums; }
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
  .toolbar .spacer, .actions .spacer, .c-head .spacer { flex: 1; }
  .card.clickable { cursor: pointer; }
  .card.clickable:hover { border-color: var(--primary-color); }
  .card.drop { border-color: var(--primary-color); border-style: dashed; }
  .card.dragging { opacity: .45; }
  /* A tile whose last row is the head or the chips must not keep their bottom gap. */
  .card > .c-head:last-child, .card > .chips:last-child { margin-bottom: 0; }
  .c-head .chev { color: var(--secondary-text-color); --mdc-icon-size: 20px; width: 20px; height: 20px; }
  .c-head .grip { color: var(--secondary-text-color); cursor: grab; flex: none;
                  --mdc-icon-size: 18px; width: 18px; height: 18px; }

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
    this._tab = "matrice";
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
  }

  _render() {
    if (!this.shadowRoot.firstChild) this._renderShell();
    const wrap = this.shadowRoot.querySelector(".wrap");
    wrap.replaceChildren();
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
    for (const key of ["volets", "matrice", "modes", "horaires", "reglages"]) {
      const b = el("button", "tab", T.tabs[key]);
      b.setAttribute("role", "tab");
      b.setAttribute("aria-selected", String(this._tab === key));
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
    else this._renderSettings(wrap);

    this._trackLiveNodes();
  }

  /* ---------- unsaved-changes guard ---------- */

  /** Snapshot taken when an editor opens; equality against it is the dirty bit. */
  _openEditor(edit) {
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
    const note = el("p", "note");
    note.textContent = T.matrixHint;
    wrap.append(note);

    const tools = el("div", "m-tools");
    const legend = el("div", "legend");
    const lg = (cls, label) => {
      const s = el("span");
      s.append(el("i", `lg ${cls}`), document.createTextNode(label));
      return s;
    };
    legend.append(lg("fixed", T.legendFixed));
    for (const key of ["none", "auto_shade", "solar_gain"]) {
      const b = el("span");
      b.append(behaviorBadge(key), document.createTextNode(T.legendBehavior[key]));
      legend.append(b);
    }
    const le = el("span");
    le.append(icon("mdi:link-variant"), document.createTextNode(T.legendEntity));
    legend.append(le, lg("empty", T.legendEmpty));
    tools.append(legend);
    wrap.append(tools);

    const scroll = el("div", "m-scroll");
    const table = el("table", "matrix");
    const thead = el("thead");
    const hr = el("tr");
    const corner = el("th", "corner");
    hr.append(corner);
    for (const m of this._cfg.modes) {
      const th = el("th");
      const mh = el("div", "mh");
      const mico = el("span", "mico");
      mico.style.background = `${m.color || "#888888"}26`;
      mico.style.color = m.color || "var(--secondary-text-color)";
      mico.append(icon(m.icon || "mdi:help-circle"));
      const flags = el("span", "flags");
      if (BEHAVIORS[m.behavior]) {
        const bf = icon(BEHAVIORS[m.behavior].icon);
        bf.style.color = BEHAVIORS[m.behavior].color;
        flags.append(bf);
      }
      if (m.lock) flags.append(icon("mdi:lock-outline"));
      if (m.priority) flags.append(icon("mdi:alert-decagram-outline"));
      if (m.duration) flags.append(icon("mdi:timer-outline"));
      if (m.hidden) flags.append(icon("mdi:eye-off-outline"));
      mh.append(mico, el("span", "", m.name), flags);
      th.append(mh);
      hr.append(th);
    }
    thead.append(hr);
    table.append(thead);

    const tbody = el("tbody");
    for (const [facade, covers] of this._grouped()) {
      if (!covers.length) continue;
      const fr = el("tr", "facade");
      const fth = el("th");
      const fl = el("div", "fl");
      fl.append(icon("mdi:compass-outline"), document.createTextNode(
        facade ? `${T.facade} ${facade}` : T.noFacade
      ));
      fth.append(fl);
      fr.append(fth);
      const fd = el("td");
      fd.colSpan = this._cfg.modes.length;
      fr.append(fd);
      tbody.append(fr);

      for (const cover of covers) {
        const tr = el("tr");
        const th = el("th");
        const rowh = el("div", "rowh");
        rowh.append(this._coverPic(cover));
        const names = el("span");
        names.append(el("span", "nm", this._coverName(cover)), el("br"),
          el("span", "fx", cover.template ? `${T.template} ${cover.template}` : T.noTemplate));
        rowh.append(names);
        th.append(rowh);
        tr.append(th);

        for (const mode of this._cfg.modes) {
          const td = el("td", "cell");
          td.append(this._cellNode(cover, mode));
          tr.append(td);
        }
        tbody.append(tr);
      }
    }
    table.append(tbody);
    scroll.append(table);
    wrap.append(scroll);
    this._matrixScroll = scroll;
  }

  _cellNode(cover, mode) {
    const cfg = (cover.modes || {})[mode.name];
    const linked = cfg !== undefined;
    const kind = cfgKind(cfg);
    let cv;
    if (!linked) {
      cv = el("div", "cv empty");
      cv.title = T.linkMode;
      cv.append(icon("mdi:plus"));
    } else if (kind === "fixed") {
      cv = el("div", "cv fixed");
      const gauge = el("span", "gauge");
      const fill = el("i");
      fill.style.width = `${cfg.value}%`;
      gauge.append(fill);
      cv.append(gauge, document.createTextNode(String(cfg.value)), el("small", "pct", "%"));
      if (mode.behavior) cv.title = T.overrideTitle;
    } else if (kind === "entity") {
      cv = el("div", "cv entity");
      cv.append(icon("mdi:link-variant"),
        document.createTextNode(String(cfg.value).split(".").pop().slice(0, 12)));
      cv.title = mode.behavior ? `${T.overrideTitle}\n${cfg.value}` : cfg.value;
    } else {
      // Three different meanings shared one primary blue: "no forced position"
      // (plain mode), "computed by shading", "computed by solar gain". The tint
      // now comes from the mode's own colour — the same one its header icon
      // already wears — so a column reads as one object top to bottom.
      // The label keeps --primary-text-color: a mode set to #FFFFFF would make
      // its own text vanish on a light theme.
      cv = el("div", "cv auto");
      const tint = mode.color || "var(--primary-color)";
      cv.style.background = `color-mix(in srgb, ${tint} 14%, transparent)`;
      cv.append(behaviorBadge(mode.behavior), el("span", "", T.auto));
    }
    cv.setAttribute("role", "button");
    cv.tabIndex = 0;
    const open = () => this._openPopover(cv, cover, mode);
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

  async _openPopover(anchor, cover, mode) {
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

    const facadeMates = this._cfg.covers.filter(
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
        const val = el("span", "val", `${state.fixed} %`);
        range.addEventListener("input", () => {
          state.fixed = Number(range.value);
          val.textContent = `${state.fixed} %`;
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
        cb.addEventListener("change", () => { state.applyFacade = cb.checked; });
        lbl.append(cb, document.createTextNode(
          facadeMates.length === 1
            ? T.applyFacadeOne(cover.facade)
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
    if (linked) {
      const unlink = el("button", "btn danger", T.unlink);
      unlink.addEventListener("click", () => this._commit(cover, mode, null, state, unlink));
      actions.append(unlink);
    }
    actions.append(el("span", "spacer"));
    const cancel = el("button", "btn ghost", T.cancel);
    cancel.addEventListener("click", () => this._closePopover());
    const save = el("button", "btn primary", linked || !isBehavior ? T.save : T.link);
    save.addEventListener("click", () => {
      let value;
      if (state.choice === "none") value = { type: "auto" };
      else if (state.choice === "fixed") value = { type: "fixed", value: Math.round(state.fixed) };
      else if (state.entity) value = { type: "entity", value: state.entity };
      else value = { type: "auto" };
      this._commit(cover, mode, value, state, save);
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

  /* ---------- form controls ---------- */

  _textRow(label, value, onInput, opts = {}) {
    const row = el("label", "field");
    row.append(el("span", "flabel", label));
    const input = document.createElement("input");
    input.type = "text";
    input.className = "ftext";
    input.value = value ?? "";
    if (opts.placeholder) input.placeholder = opts.placeholder;
    input.addEventListener("input", () => onInput(input.value));
    row.append(input);
    return row;
  }

  _selectRow(label, value, options, onChange) {
    const row = el("label", "field");
    row.append(el("span", "flabel", label));
    const sel = document.createElement("select");
    sel.className = "fselect";
    for (const [val, text] of options) {
      const o = document.createElement("option");
      o.value = val === null ? "" : String(val);
      o.textContent = text;
      if ((value ?? "") === (val ?? "")) o.selected = true;
      sel.append(o);
    }
    sel.addEventListener("change", () => onChange(sel.value || null));
    row.append(sel);
    return row;
  }

  _boolRow(label, value, onChange, hint) {
    const row = el("label", "field switch");
    const box = el("span", "flabel");
    box.append(document.createTextNode(label));
    if (hint) box.append(el("small", "fhint", hint));
    row.append(box);
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = !!value;
    cb.addEventListener("change", () => onChange(cb.checked));
    row.append(cb);
    return row;
  }

  /** A slider with no inheritance behind it (facade azimuth, and the like). */
  _sliderRow(label, value, spec, onInput) {
    const row = el("div", "field num");
    const head = el("div", "fhead");
    head.append(el("span", "flabel", label));
    const fmt = (v) => `${v}${spec.unit ? ` ${spec.unit}` : ""}`;
    const val = el("span", "fval", fmt(value));
    head.append(val);
    row.append(head);

    const range = document.createElement("input");
    range.type = "range";
    range.min = String(spec.min);
    range.max = String(spec.max);
    range.step = String(spec.step || 1);
    range.value = String(value);
    range.addEventListener("input", () => {
      const n = Number(range.value);
      val.textContent = fmt(n);
      onInput(n);
    });
    row.append(range);
    return row;
  }

  /** A typed number, for values a slider would make imprecise (milliseconds). */
  _numberRow(label, value, spec, onInput, hint) {
    const row = el("label", "field");
    const box = el("span", "flabel");
    box.append(document.createTextNode(label));
    if (hint) box.append(el("small", "fhint", hint));
    row.append(box);
    const input = document.createElement("input");
    input.type = "number";
    input.className = "ftext fnum";
    input.min = String(spec.min);
    input.max = String(spec.max);
    input.step = String(spec.step || 1);
    input.value = String(value);
    input.addEventListener("input", () => {
      // An empty box is a transient state while typing, not a zero.
      if (input.value !== "") onInput(Number(input.value));
    });
    row.append(input);
    if (spec.unit) row.append(el("span", "funit", spec.unit));
    return row;
  }

  /** A HA selector row (icon, colour, entity…), loaded lazily like the popover. */
  _selectorRow(label, selector, value, onChange, hint) {
    const row = el("div", "field vertical");
    row.append(el("span", "flabel", label));
    if (hint) row.append(el("small", "fhint", hint));
    const sel = document.createElement("ha-selector");
    sel.hass = this._hass;
    sel.selector = selector;
    sel.value = value ?? undefined;
    sel.addEventListener("value-changed", (e) => onChange(e.detail.value));
    row.append(sel);
    return row;
  }

  /**
   * One behavior field. The value shown is always the EFFECTIVE one; the row is
   * flagged when the cover overrides its template, and the flag doubles as the
   * way back — clicking it drops the override instead of hunting for the
   * template's number.
   */
  _behaviorRow(name, spec, draft, baseline, rerender, hasTemplate) {
    const overridden = Object.prototype.hasOwnProperty.call(draft, name);
    const value = overridden ? draft[name] : baseline[name];

    if (spec.type === "boolean") {
      // Activation flags are cover-specific: no template value to fall back to.
      return this._boolRow(T.fields[name] || name, value, (v) => { draft[name] = v; });
    }

    const row = el("div", "field num");
    const head = el("div", "fhead");
    head.append(el("span", "flabel", T.fields[name] || name));

    // Built once and merely hidden, never re-created: rebuilding the row on the
    // first slider move would tear the input out from under the pointer and
    // abort the drag. Without a template there is nothing to revert TO, so the
    // affordance stays out of the way entirely.
    // Icon only: the amber row already announces the departure, so a label
    // beside it would say the same thing twice. What is left for the control to
    // carry is the action, and the tooltip names it.
    const reset = el("button", "revert");
    reset.type = "button";
    reset.title = T.revertTitle;
    reset.setAttribute("aria-label", T.revertTitle);
    reset.append(icon("mdi:backup-restore"));
    reset.addEventListener("click", () => { delete draft[name]; rerender(); });
    head.append(reset);

    const fmt = (v) => `${v}${spec.unit ? ` ${spec.unit}` : ""}`;
    const val = el("span", "fval", fmt(value));
    head.append(val);
    row.append(head);

    const mark = (on) => {
      row.classList.toggle("ovr", on && hasTemplate);
      reset.hidden = !(on && hasTemplate);
    };
    mark(overridden);

    const range = document.createElement("input");
    range.type = "range";
    range.min = String(spec.min);
    range.max = String(spec.max);
    range.step = String(spec.step || 1);
    range.value = String(value);
    range.addEventListener("input", () => {
      const raw = Number(range.value);
      const n = spec.step && spec.step < 1 ? Math.round(raw * 10) / 10 : Math.round(raw);
      draft[name] = n;
      val.textContent = fmt(n);
      mark(true);
    });
    row.append(range);
    return row;
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
                 duration: null, return_mode: null },
      });
      this._render();
    });
    bar.append(add, el("span", "spacer"), el("span", "hint", T.dragHint));
    wrap.append(bar);

    const grid = el("div", "grid");

    this._cfg.modes.forEach((m, i) => {
      const card = el("div", "card clickable");
      card.tabIndex = 0;
      card.draggable = true;
      const open = () => {
        this._openEditor({ section: "mode", idx: i, draft: { ...m } });
        this._render();
      };
      card.addEventListener("click", open);
      card.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
      });
      card.addEventListener("dragstart", (e) => {
        this._dragFrom = i;
        e.dataTransfer.effectAllowed = "move";
        card.classList.add("dragging");
      });
      card.addEventListener("dragend", () => card.classList.remove("dragging"));
      card.addEventListener("dragover", (e) => { e.preventDefault(); card.classList.add("drop"); });
      card.addEventListener("dragleave", () => card.classList.remove("drop"));
      card.addEventListener("drop", (e) => {
        e.preventDefault();
        card.classList.remove("drop");
        this._reorderModes(this._dragFrom, i);
      });

      const head = el("div", "c-head");
      // The rank is spelled out: a wrapping grid reads left-to-right, which is
      // the selector's order, but the number says so without relying on layout.
      head.append(el("span", "m-ord", String(i + 1)));
      const mico = el("span", "mico");
      mico.style.background = `color-mix(in srgb, ${m.color || "#888888"} 16%, transparent)`;
      mico.style.color = m.color || "var(--secondary-text-color)";
      mico.append(icon(m.icon || "mdi:help-circle"));
      const names = el("span");
      names.append(el("span", "nm", m.name), el("br"),
        el("span", "meta", T.covers(usage[m.name] || 0)));
      head.append(mico, names, el("span", "spacer"),
        icon("mdi:drag-horizontal-variant", "grip"), icon("mdi:chevron-right", "chev"));
      card.append(head);

      const chips = el("div", "chips");
      if (m.behavior) {
        const c = el("span", "chip auto");
        c.append(icon(m.behavior === "auto_shade" ? "mdi:weather-sunny" : "mdi:thermometer"),
          document.createTextNode(m.behavior === "auto_shade" ? T.shading : T.solarGain));
        chips.append(c);
      }
      if (m.lock) {
        const c = el("span", "chip lock");
        c.append(icon("mdi:lock-outline"), document.createTextNode(T.lock));
        chips.append(c);
      }
      if (m.duration) {
        const c = el("span", "chip timer");
        c.append(icon("mdi:timer-outline"), document.createTextNode(T.timedChip(m.duration, m.return_mode)));
        chips.append(c);
      }
      if (m.priority) {
        const c = el("span", "chip prio");
        c.append(icon("mdi:alert-decagram-outline"), document.createTextNode(T.priority));
        chips.append(c);
      }
      if (m.hidden) {
        const c = el("span", "chip");
        c.append(icon("mdi:eye-off-outline"), document.createTextNode(T.hidden));
        chips.append(c);
      }
      if (chips.childElementCount) card.append(chips);

      grid.append(card);
    });

    wrap.append(grid);
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

    const bar = el("div", "toolbar");
    const back = el("button", "btn ghost");
    back.append(icon("mdi:arrow-left"), document.createTextNode(T.backToModes));
    back.addEventListener("click", () => { if (this._leaveEditor()) this._render(); });
    bar.append(back);
    wrap.append(bar);

    const host = el("div", "card");
    host.append(el("h3", "sec", creating ? T.newMode : draft.name || T.mode));

    host.append(this._textRow(T.name, draft.name, (v) => { draft.name = v; }));
    host.append(this._selectorRow(T.icon, { icon: {} }, draft.icon,
      (v) => { draft.icon = v || "mdi:help-circle"; }));
    host.append(this._selectorRow(T.color, { color_rgb: {} }, hexToRgb(draft.color),
      (v) => { draft.color = rgbToHex(v); }));
    host.append(this._selectRow(T.behavior, draft.behavior, [
      [null, T.behaviorNone], ["auto_shade", T.shading], ["solar_gain", T.solarGain],
    ], (v) => { draft.behavior = v; rerender(); }));
    if (draft.behavior) host.append(el("p", "hint", T.behaviorHint));
    host.append(this._boolRow(T.lockField, draft.lock, (v) => { draft.lock = v; }, T.lockHint));
    host.append(this._boolRow(T.priorityField, draft.priority, (v) => { draft.priority = v; }, T.priorityHint));
    // A mode other modes return to cannot take a duration (the server refuses
    // it too): say so before the user tries, rather than after the save.
    const returners = creating ? [] : this._cfg.modes
      .filter((m) => m.duration && m.return_mode === this._cfg.modes[idx].name)
      .map((m) => m.name);
    host.append(this._boolRow(T.durationField, !!draft.duration, (v) => {
      draft.duration = v ? (draft.duration || 60) : null;
      if (!v) draft.return_mode = null;
      rerender();
    }, returners.length ? T.usedAsReturn(returners) : T.durationHint));
    if (draft.duration) {
      host.append(this._numberRow(T.durationLabel, draft.duration,
        { min: 1, max: 1440, step: 1, unit: "min" }, (v) => { draft.duration = v; }));
      // Only modes without a duration: every countdown must end on a mode
      // that starts no other (the server refuses anything else too).
      const targets = this._cfg.modes.filter((m) => !m.duration && m.name !== draft.name);
      host.append(this._selectRow(T.returnField, draft.return_mode,
        [[null, T.returnBase], ...targets.map((m) => [m.name, m.name])],
        (v) => { draft.return_mode = v; }));
      host.append(el("p", "hint", T.returnHint));
    }
    host.append(this._boolRow(T.hiddenField, draft.hidden, (v) => { draft.hidden = v; }, T.hiddenHint));
    wrap.append(host);

    const actions = el("div", "actions card");
    if (!creating) {
      const used = usage[draft.name] || 0;
      const del = el("button", "btn danger");
      del.append(icon("mdi:delete-outline"), document.createTextNode(T.delete));
      if (used) {
        del.disabled = true;
        del.title = T.inUseTitle(used);
      } else {
        del.addEventListener("click", () => {
          const items = this._cfg.modes.filter((_, i) => i !== idx).map((m) => ({ ...m }));
          this._saveSection("mode", items);
        });
      }
      actions.append(del);
    }
    actions.append(el("span", "spacer"));
    const cancel = el("button", "btn ghost", T.cancel);
    cancel.addEventListener("click", () => { if (this._leaveEditor()) this._render(); });
    const save = el("button", "btn primary", T.save);
    save.addEventListener("click", () => {
      const items = this._cfg.modes.map((m) => ({ ...m }));
      if (creating) items.push(draft); else items[idx] = draft;
      this._saveSection("mode", items);
    });
    actions.append(cancel, save);
    wrap.append(actions);
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
    bar.append(add);
    wrap.append(bar);

    const grid = el("div", "grid");
    for (const [facade, covers] of this._grouped()) {
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

        const head = el("div", "c-head");
        head.append(this._coverPic(c));
        const names = el("span");
        names.append(el("span", "nm", this._coverName(c)), el("br"), el("span", "eid", c.entity_id));
        head.append(names);
        head.append(el("span", "spacer"), icon("mdi:chevron-right", "chev"));
        card.append(head);
        const status = this._statusLine(c);
        if (status) card.append(status);

        const chips = el("div", "chips");
        const fchip = el("span", "chip");
        fchip.append(icon("mdi:compass-outline"), document.createTextNode(facade || T.noFacade));
        chips.append(fchip);
        if (c.template) {
          const tchip = el("span", "chip");
          tchip.append(icon("mdi:ruler-square"), document.createTextNode(c.template));
          chips.append(tchip);
        }
        chips.append(el("span", "chip", T.modesCount(Object.keys(c.modes || {}).length)));
        const overrides = this._overrideCount(c);
        if (overrides) {
          const ochip = el("span", "chip ovr");
          ochip.append(icon("mdi:pencil-outline"), document.createTextNode(T.overrides(overrides)));
          chips.append(ochip);
        }
        card.append(chips);

        const feats = el("div", "feats");
        const sh = el("span", c.shade_enable ? "on" : "");
        sh.append(icon("mdi:weather-sunny"), document.createTextNode(` ${T.shading} ${c.shade_enable ? T.active : "—"}`));
        const sg = el("span", c.solar_gain_enable ? "on" : "");
        sg.append(icon("mdi:thermometer"), document.createTextNode(` ${T.solarGain} ${c.solar_gain_enable ? T.activeF : "—"}`));
        feats.append(sh, sg);
        card.append(feats);
        grid.append(card);
      }
    }
    wrap.append(grid);
  }

  /** Every state the cover cards show, as one string: the redraw trigger. */
  _statusSignature() {
    const st = this._hass?.states || {};
    const parts = [];
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
    const pill = el("span", "smode");
    pill.style.background = `color-mix(in srgb, ${mode?.color || "#888888"} 16%, transparent)`;
    pill.append(icon(mode?.icon || "mdi:help-circle"), document.createTextNode(sel.state));
    line.append(pill);
    const pos = st[c.entity_id]?.attributes?.current_position;
    if (pos != null) line.append(el("span", "spos", `${pos} %`));
    const chip = (cls, ico, text, title) => {
      const ch = el("span", `chip ${cls}`);
      ch.append(icon(ico), document.createTextNode(text));
      if (title) ch.title = title;
      line.append(ch);
    };
    const ends = sel.attributes?.mode_ends_at;
    if (ends) {
      const at = new Date(ends).toLocaleTimeString(LANG, { hour: "2-digit", minute: "2-digit" });
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

    const bar = el("div", "toolbar");
    const back = el("button", "btn ghost");
    back.append(icon("mdi:arrow-left"), document.createTextNode(T.backToCovers));
    back.addEventListener("click", () => { if (this._leaveEditor()) this._render(); });
    bar.append(back);
    wrap.append(bar);

    const tpl = this._templateOf(draft);
    const baseline = this._baseline(draft);

    /* identity */
    const idCard = el("div", "card");
    idCard.append(el("h3", "sec", creating ? T.newCover : this._coverName(draft)));
    idCard.append(this._selectorRow(T.entity, { entity: { domain: ["cover"] } },
      draft.entity_id || undefined, (v) => { draft.entity_id = v || ""; }));
    idCard.append(this._textRow(T.picture, draft.entity_picture,
      (v) => { draft.entity_picture = v || undefined; }, { placeholder: "/local/…" }));
    idCard.append(this._selectRow(T.facade, draft.facade,
      this._cfg.facades.map((f) => [f.name, f.name]), (v) => { draft.facade = v; }));
    idCard.append(this._selectRow(T.templateTitle, draft.template,
      [[null, T.noTemplateOpt], ...this._cfg.templates.map((t) => [t.name, t.name])],
      (v) => { draft.template = v; rerender(); }));
    idCard.append(this._selectorRow(T.exclusion, { entity: { multiple: true } },
      draft.exclusion?.length ? draft.exclusion : undefined,
      (v) => { draft.exclusion = v || []; }, T.exclusionHint));
    idCard.append(this._selectorRow(T.inhibition, { entity: { multiple: true } },
      draft.inhibition?.length ? draft.inhibition : undefined,
      (v) => { draft.inhibition = v || []; }, T.inhibitionHint));
    wrap.append(idCard);

    /* behavior, section by section */
    const schema = this._cfg.behavior;
    if (schema) {
      const note = el("p", "note");
      note.textContent = tpl ? T.tplNote(tpl.name) : T.noTplNote;
      wrap.append(note);

      for (const { key, fields } of schema.sections) {
        const det = document.createElement("details");
        det.className = "sect";
        if (this._openSections?.has(key)) det.open = true;
        det.addEventListener("toggle", () => {
          this._openSections = this._openSections || new Set();
          if (det.open) this._openSections.add(key); else this._openSections.delete(key);
        });
        const sum = document.createElement("summary");
        sum.append(icon(SECTION_ICONS[key] || "mdi:tune"), document.createTextNode(T.sections[key] || key));
        const n = tpl ? fields.filter((f) => schema.fields[f].type !== "boolean"
          && Object.prototype.hasOwnProperty.call(draft, f)).length : 0;
        if (n) sum.append(el("span", "mini ovr", T.overrides(n)));
        det.append(sum);
        for (const name of fields) {
          det.append(this._behaviorRow(name, schema.fields[name], draft, baseline, rerender, !!tpl));
        }
        wrap.append(det);
      }
    }

    const actions = el("div", "actions card");
    if (!creating) {
      const del = el("button", "btn danger");
      del.append(icon("mdi:delete-outline"), document.createTextNode(T.delete));
      del.addEventListener("click", () => {
        const items = this._cfg.covers.filter((_, i) => i !== idx)
          .map((c) => JSON.parse(JSON.stringify(c)));
        this._saveSection("cover", items);
      });
      actions.append(del);
    }
    actions.append(el("span", "spacer"));
    const cancel = el("button", "btn ghost", T.cancel);
    cancel.addEventListener("click", () => { if (this._leaveEditor()) this._render(); });
    const save = el("button", "btn primary", T.save);
    save.addEventListener("click", () => {
      const items = this._cfg.covers.map((c) => JSON.parse(JSON.stringify(c)));
      if (creating) items.push(draft); else items[idx] = draft;
      this._saveSection("cover", items);
    });
    actions.append(cancel, save);
    wrap.append(actions);
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

    wrap.append(el("p", "note", W.intro));

    /* ---- curve editor ---- */
    const card = el("div", "card sched blk");
    const head = el("div", "toolbar");
    const seg = el("div", "seg sched-seg");
    for (const k of SCHED_KINDS) {
      const b = el("button", k === kind ? "on" : "", W.kinds[k]);
      b.type = "button";
      b.addEventListener("click", () => { this._schedKind = k; this._render(); });
      seg.append(b);
    }
    const sub = el("span", "secsub", `${W.refWord} : ${W.refLong[kind]}`);
    head.append(seg, el("span", "spacer"), sub);
    card.append(head);
    card.append(this._boolRow(W.enable[kind], draft.enabled[kind], (v) => {
      draft.enabled[kind] = v; this._render();
    }, W.enableHint[kind]));

    const body = el("div", "sched-body");
    body.hidden = !draft.enabled[kind];
    card.append(body);
    const hint = el("p", "hint");
    body.append(hint);

    const fields = el("div", "sched-fields");
    const mkField = (color, label, type, toggle) => {
      const box = el("div", "sf");
      box.style.setProperty("--c", color);
      const top = el("div", "sf-top");
      const lab = el("label", "", label);
      top.append(lab);
      let cb = null;
      if (toggle) {
        cb = document.createElement("input");
        cb.type = "checkbox";
        cb.setAttribute("aria-label", label);
        top.append(cb);
      }
      const input = document.createElement("input");
      input.type = type;
      const info = el("span", "sf-info");
      box.append(top, input, info);
      fields.append(box);
      return { box, input, cb, info, lab };
    };
    const F = {
      hi: mkField("var(--ce-h)", W.hi, "time"),
      x1: mkField("var(--ce-x)", W.x1, "date", true),
      fl: mkField("var(--ce-clamp)", W.fl, "time", true),
      lo: mkField("var(--ce-h)", W.lo, "time"),
      x2: mkField("var(--ce-x)", W.x2, "date", true),
      ce: mkField("var(--ce-clamp)", W.ce, "time", true),
    };
    body.append(fields);

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
    body.append(stats);
    wrap.append(card);

    /* ---- per-cover mode ---- */
    const tcard = el("div", "card blk");
    tcard.append(el("h3", "sec", W.perCover), el("p", "secsub", W.perCoverSub));
    const scroll = el("div", "t-scroll");
    const table = el("table", "assign");
    const hr = el("tr");
    const timeCells = {};
    hr.append(el("th", "", W.cover));
    for (const k of SCHED_KINDS) { timeCells[k] = el("th"); hr.append(timeCells[k]); }
    const thead = el("thead"); thead.append(hr); table.append(thead);
    const timed = new Set(this._cfg.modes.filter((m) => m.duration).map((m) => m.name));
    const tbody = el("tbody");
    for (const c of this._cfg.covers) {
      const tr = el("tr");
      const th = el("td");
      const rowh = el("div", "rowh");
      rowh.append(this._coverPic(c));
      const names = el("span");
      names.append(el("span", "nm", this._coverName(c)), el("br"), el("span", "fx", c.entity_id));
      rowh.append(names);
      th.append(rowh);
      tr.append(th);
      const opts = [[null, W.noneOpt], ...Object.keys(c.modes || {}).filter((m) => !timed.has(m)).map((m) => [m, m])];
      for (const k of SCHED_KINDS) {
        const td = el("td");
        const sel = document.createElement("select");
        sel.className = "fselect";
        sel.setAttribute("aria-label", `${W.kinds[k]}, ${this._coverName(c)}`);
        for (const [val, text] of opts) {
          const o = document.createElement("option");
          o.value = val ?? "";
          o.textContent = text;
          if ((draft.assign[c.entity_id][k] ?? "") === (val ?? "")) o.selected = true;
          sel.append(o);
        }
        sel.disabled = !draft.enabled[k];
        sel.addEventListener("change", () => { draft.assign[c.entity_id][k] = sel.value || null; });
        td.append(sel);
        tr.append(td);
      }
      tbody.append(tr);
    }
    table.append(tbody);
    scroll.append(table);
    tcard.append(scroll);
    wrap.append(tcard);

    /* ---- actions ---- */
    const actions = el("div", "actions card");
    actions.append(el("span", "spacer"));
    const cancel = el("button", "btn ghost", T.cancel);
    cancel.addEventListener("click", () => { if (this._leaveEditor()) this._render(); });
    const save = el("button", "btn primary", T.save);
    save.addEventListener("click", () => {
      const house = {};
      for (const k of SCHED_KINDS) if (draft.enabled[k]) house[k] = schedToCfg(draft.s[k]);
      this._saveSection("schedule", { house, covers: draft.assign });
    });
    actions.append(cancel, save);
    wrap.append(actions);

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
      if (pts && sun) {
        let seg2 = [], nBefore = 0, nX = 0, prev = null, aMax = -1e9, aJ = 1, bMax = -1e9, bJ = 1, eJ = 1, lJ = 1;
        const flush = () => {
          if (seg2.length > 1) mk("polygon", { points: seg2.map((j) => `${xOf(j)},${yOf(sun[j - 1])}`).concat(seg2.slice().reverse().map((j) => `${xOf(j)},${yOf(pts[j - 1])}`)).join(" "), class: "band" });
          seg2 = [];
        };
        for (let j = 1; j <= 365; j++) {
          const d = pts[j - 1] - sun[j - 1], before = d < 0;
          if (before) { seg2.push(j); nBefore++; } else flush();
          if (d > aMax) { aMax = d; aJ = j; }
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
        st = [
          [W.today, hmFmt(pts[today - 1]), `${W.ref[kind]} ${hmFmt(sun[today - 1])}`],
          [W.earliest, hmFmt(pts[eJ - 1]), W.onDate(schedDayLabel(eJ, year, "long"))],
          [W.latest, hmFmt(pts[lJ - 1]), W.onDate(schedDayLabel(lJ, year, "long"))],
          [W.maxAfter(W.ref[kind]), signedMin(aMax), W.onDate(schedDayLabel(aJ, year, "long"))],
          [W.daysBefore(W.ref[kind]), String(nBefore), nBefore ? W.upTo(signedMin(-bMax), schedDayLabel(bJ, year, "long")) : W.none],
        ];
      }
      warn.hidden = !msgs.length;
      warn.replaceChildren(...msgs.map((m) => el("div", "", m)));
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
      hint.textContent = W.fixedHint + (G ? W.dstHint(G / 60) : "") + W.dblHint;
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
      }
    };

    const refresh = () => this._schedRequest(kind, redraw);
    const changed = () => { redraw(); refresh(); };

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
   * Three things live here, and only two of them are lists: facades and
   * templates get the tile grid every other tab uses, while the global settings
   * are a single item — a grid of one would be a lie, so they are a plain form.
   */
  _renderSettings(wrap) {
    if (this._edit?.section === "facade") { this._facadeEditor(wrap); return; }
    if (this._edit?.section === "template") { this._templateEditor(wrap); return; }

    this._renderFacadeList(wrap);
    this._renderTemplateList(wrap);
    this._renderGlobal(wrap);
    this._renderEntities(wrap);
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

    const head = el("div", "toolbar section-head");
    const title = el("span");
    title.append(el("h3", "sec", T.entitiesSec), el("p", "secsub", T.entitiesSub));
    head.append(title);
    wrap.append(head);

    const card = el("div", "card");
    const grid = el("div", "stats");
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

  _renderFacadeList(wrap) {
    const used = this._refCount("facade");
    const head = el("div", "toolbar");
    const title = el("span");
    title.append(el("h3", "sec", T.facades), el("p", "secsub", T.facadesSub));
    const add = el("button", "btn primary");
    add.append(icon("mdi:plus"), document.createTextNode(T.addFacade));
    add.addEventListener("click", () => {
      this._openEditor({ section: "facade", idx: -1, draft: { name: "", azimuth: 180 } });
      this._render();
    });
    head.append(title, el("span", "spacer"), add);
    wrap.append(head);

    const grid = el("div", "grid");
    this._cfg.facades.forEach((f, i) => {
      const card = this._tile("mdi:compass-outline", f.name, `${Number(f.azimuth ?? 180)}°`, () => {
        this._openEditor({ section: "facade", idx: i, draft: { ...f } });
        this._render();
      });
      const chips = el("div", "chips");
      chips.append(el("span", "chip", T.covers(used[f.name] || 0)));
      card.append(chips);
      grid.append(card);
    });
    wrap.append(grid);
  }

  _renderTemplateList(wrap) {
    const used = this._refCount("template");
    const head = el("div", "toolbar section-head");
    const title = el("span");
    title.append(el("h3", "sec", T.templates), el("p", "secsub", T.templatesSub));
    const add = el("button", "btn primary");
    add.append(icon("mdi:plus"), document.createTextNode(T.addTemplate));
    add.addEventListener("click", () => {
      const draft = { name: "" };
      for (const [name, spec] of Object.entries(this._cfg.behavior?.fields || {})) {
        if (spec.type !== "boolean") draft[name] = spec.default;
      }
      this._openEditor({ section: "template", idx: -1, draft });
      this._render();
    });
    head.append(title, el("span", "spacer"), add);
    wrap.append(head);

    const grid = el("div", "grid");
    this._cfg.templates.forEach((t, i) => {
      const sub = `H ${t.shade_max_height ?? "?"} m · D ${t.shade_distance ?? "?"} m`;
      const card = this._tile("mdi:ruler-square", t.name, sub, () => {
        this._openEditor({ section: "template", idx: i, draft: { ...t } });
        this._render();
      });
      const chips = el("div", "chips");
      chips.append(el("span", "chip", T.covers(used[t.name] || 0)));
      card.append(chips);
      grid.append(card);
    });
    wrap.append(grid);
  }

  /** The tile shell shared by facades and templates. */
  _tile(iconName, name, meta, open) {
    const card = el("div", "card clickable");
    card.tabIndex = 0;
    card.addEventListener("click", open);
    card.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
    });
    const head = el("div", "c-head");
    const pic = el("span", "pic");
    pic.append(icon(iconName));
    const names = el("span");
    names.append(el("span", "nm", name), el("br"), el("span", "meta", meta));
    head.append(pic, names, el("span", "spacer"), icon("mdi:chevron-right", "chev"));
    card.append(head);
    return card;
  }

  _facadeEditor(wrap) {
    const { idx, draft } = this._edit;
    const creating = idx < 0;
    const used = this._refCount("facade")[draft.name] || 0;

    wrap.append(this._backBar(T.backToFacades));

    const card = el("div", "card");
    card.append(el("h3", "sec", creating ? T.newFacade : draft.name || T.facade));
    card.append(this._textRow(T.name, draft.name, (v) => { draft.name = v; }));
    card.append(this._sliderRow(T.azimuth, Number(draft.azimuth ?? 180),
      { min: 0, max: 360, step: 1, unit: "°" }, (v) => { draft.azimuth = v; }));
    card.append(el("p", "hint", T.facadesSub));
    wrap.append(card);

    wrap.append(this._itemActions("facade", "facades", idx, draft, creating, used));
  }

  _templateEditor(wrap) {
    const { idx, draft } = this._edit;
    const creating = idx < 0;
    const used = this._refCount("template")[draft.name] || 0;
    const schema = this._cfg.behavior;

    wrap.append(this._backBar(T.backToTemplates));

    const card = el("div", "card");
    card.append(el("h3", "sec", creating ? T.newTemplate : draft.name || T.templateTitle));
    card.append(this._textRow(T.name, draft.name, (v) => { draft.name = v; }));
    wrap.append(card);

    if (schema) {
      wrap.append(el("p", "note", T.tplNoOverrideNote));
      // Same rows as a cover, minus the amber: passing no template means
      // _behaviorRow finds nothing to revert to and keeps the affordance hidden.
      for (const { key, fields } of (schema.template_sections || schema.sections)) {
        const det = document.createElement("details");
        det.className = "sect";
        if (this._openSections?.has(key)) det.open = true;
        det.addEventListener("toggle", () => {
          this._openSections = this._openSections || new Set();
          if (det.open) this._openSections.add(key); else this._openSections.delete(key);
        });
        const sum = document.createElement("summary");
        sum.append(icon(SECTION_ICONS[key] || "mdi:tune"),
          document.createTextNode(T.sections[key] || key));
        det.append(sum);
        for (const name of fields) {
          det.append(this._behaviorRow(name, schema.fields[name], draft, {},
            () => this._render(), false));
        }
        wrap.append(det);
      }
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
    const actions = el("div", "actions card");
    if (!creating) {
      const del = el("button", "btn danger");
      del.append(icon("mdi:delete-outline"), document.createTextNode(T.delete));
      if (used) {
        del.disabled = true;
        del.title = T.inUseItemTitle(used);
      } else {
        del.addEventListener("click", () => {
          this._saveSection(section, this._cfg[key].filter((_, i) => i !== idx).map((it) => ({ ...it })));
        });
      }
      actions.append(del);
    }
    actions.append(el("span", "spacer"));
    const cancel = el("button", "btn ghost", T.cancel);
    cancel.addEventListener("click", () => { if (this._leaveEditor()) this._render(); });
    const save = el("button", "btn primary", T.save);
    save.addEventListener("click", () => {
      const items = this._cfg[key].map((it) => ({ ...it }));
      if (creating) items.push(draft); else items[idx] = draft;
      this._saveSection(section, items);
    });
    actions.append(cancel, save);
    return actions;
  }

  /**
   * Global settings. A single item, so it is edited in place: the draft lives on
   * the instance, not in _edit, and survives the re-renders a selector triggers.
   */
  _renderGlobal(wrap) {
    const draft = this._globalDraft || (this._globalDraft = { ...(this._cfg.global || {}) });
    // Pristine copy for the unsaved-changes guard: these settings are edited in
    // place, so there is no editor object to hang a snapshot off.
    if (this._globalClean === null) this._globalClean = JSON.stringify(draft);
    const conditions = this._cfg.weather_conditions || [];
    const interval = this._cfg.defaults?.command_interval ?? 150;

    const head = el("div", "toolbar section-head");
    const title = el("span");
    title.append(el("h3", "sec", T.globalSettings), el("p", "secsub", T.globalSub));
    head.append(title);
    wrap.append(head);

    const card = el("div", "card");
    card.append(this._numberRow(T.interval, draft.command_interval ?? interval,
      { min: 0, max: 5000, step: 10, unit: "ms" },
      (v) => { draft.command_interval = v; }, T.intervalHint));
    card.append(this._selectorRow(T.tempEntity,
      { entity: { domain: "sensor", device_class: "temperature" } },
      draft.sg_temperature_entity || undefined,
      (v) => { draft.sg_temperature_entity = v || undefined; }));
    card.append(this._selectorRow(T.threshold,
      { entity: { domain: ["input_number", "number"] } },
      draft.sg_temperature_threshold || undefined,
      (v) => { draft.sg_temperature_threshold = v || undefined; }));
    card.append(this._selectorRow(T.weather, { entity: { domain: "weather" } },
      draft.sg_weather_entity || undefined,
      (v) => { draft.sg_weather_entity = v || undefined; }));
    card.append(this._selectorRow(T.goodConditions, {
      select: {
        multiple: true, mode: "dropdown", sort: false,
        options: conditions.map((c) => ({ value: c, label: T.weatherStates[c] || c })),
      },
    }, draft.sg_good_conditions ?? ["sunny", "partlycloudy"],
      (v) => { draft.sg_good_conditions = v || []; }));
    card.append(el("p", "hint", T.goodConditionsHint));
    wrap.append(card);

    const disp = el("div", "card");
    disp.append(el("h3", "sec", T.display));
    disp.append(this._boolRow(T.showSunFacing, draft.show_sun_facing ?? true,
      (v) => { draft.show_sun_facing = v; }));
    disp.append(this._boolRow(T.showAutoShade, draft.show_auto_shade ?? true,
      (v) => { draft.show_auto_shade = v; }));
    disp.append(this._boolRow(T.showSolarGain, draft.show_solar_gain ?? false,
      (v) => { draft.show_solar_gain = v; }));
    wrap.append(disp);

    const actions = el("div", "actions card");
    actions.append(el("span", "spacer"));
    const cancel = el("button", "btn ghost", T.cancel);
    cancel.addEventListener("click", () => { if (this._leaveEditor()) this._render(); });
    const save = el("button", "btn primary", T.save);
    save.addEventListener("click", () => { this._saveSection("global", { ...draft }); });
    actions.append(cancel, save);
    wrap.append(actions);
  }
}

customElements.define("cover-extender-panel", CoverExtenderPanel);
