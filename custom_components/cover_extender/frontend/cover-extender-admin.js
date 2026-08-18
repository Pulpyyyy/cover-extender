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
    tabs: { matrice: "Matrix", volets: "Covers", modes: "Modes", reglages: "Settings" },
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
    noneHint: "No position forced: the cover stays where it is (locked if the mode locks).",
    entityHint: "The entity's value drives the position live.",
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
    showAutoShade: "“Automatic shading” switch",
    showSolarGain: "“Solar gain” switch",
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
    behaviorHint: "Per-cover positions no longer apply: they are computed.",
    lockField: "Lock the covers",
    lockHint: "Blocks every manual command while the mode is on.",
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
    exclusion: "Exclusion entities",
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
    tabs: { matrice: "Matrice", volets: "Volets", modes: "Modes", reglages: "Réglages" },
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
    noneHint: "Pas de position forcée : le volet reste en place (verrouille si mode verrou).",
    entityHint: "La valeur de l'entité pilote la position en direct.",
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
    showAutoShade: "Interrupteur « ombrage automatique »",
    showSolarGain: "Interrupteur « héliotropie »",
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
    behaviorHint: "Les positions par volet ne s'appliquent plus : elles sont calculées.",
    lockField: "Verrouiller les volets",
    lockHint: "Empêche toute commande manuelle tant que le mode est actif.",
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
    exclusion: "Entités d'exclusion",
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

  @media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
`;

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
    for (const key of ["volets", "matrice", "modes", "reglages"]) {
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
    } else if (kind === "entity") {
      cv = el("div", "cv entity");
      cv.append(icon("mdi:link-variant"),
        document.createTextNode(String(cfg.value).split(".").pop().slice(0, 12)));
      cv.title = cfg.value;
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
      if (isBehavior) {
        body.append(el("p", "sub", T.behaviorSub[mode.behavior]));
      } else {
        body.append(el("p", "sub", T.posSub));
        const seg = el("div", "seg");
        const segs = [["fixed", T.segFixed], ["entity", T.segEntity], ["none", T.segNone]];
        for (const [key, label] of segs) {
          const b = el("button", state.choice === key ? "on" : "", label);
          b.addEventListener("click", () => { state.choice = key; renderBody(); });
          seg.append(b);
        }
        body.append(seg);

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
          body.append(el("p", "hint", T.noneHint));
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
      }
      // Switching segment changes the height a lot (the entity picker is tall):
      // re-clamp so the popover never overflows the viewport. No-op before mount.
      this._anchorPopover();
    };

    // ha-selector needs the editor chunk; load it before first entity render.
    if (!isBehavior) await loadHaForm();
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
      if (isBehavior || state.choice === "none") value = { type: "auto" };
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
  _selectorRow(label, selector, value, onChange) {
    const row = el("div", "field vertical");
    row.append(el("span", "flabel", label));
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
                 lock: false, behavior: null, hidden: false },
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

  /** Drag reorder. The stored order drives the order of the select.mode_* options. */
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
                 template: null, exclusion: [], modes: {},
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
    idCard.append(this._selectRow(T.template, draft.template,
      [[null, T.noTemplateOpt], ...this._cfg.templates.map((t) => [t.name, t.name])],
      (v) => { draft.template = v; rerender(); }));
    idCard.append(this._selectorRow(T.exclusion, { entity: { multiple: true } },
      draft.exclusion?.length ? draft.exclusion : undefined,
      (v) => { draft.exclusion = v || []; }));
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
