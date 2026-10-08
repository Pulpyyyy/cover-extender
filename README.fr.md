# Cover Extender

🇬🇧 [English version](README.md) (référence complète : entités, actions, événements)

Cover Extender est une intégration Home Assistant qui ajoute des [modes](#modes) (dont des [modes minutés](#modes-minutés)), un [verrou avec mémoire de position](#verrou-et-mémoire), des [exclusions et inhibitions](#exclusions), des [horaires du matin et du soir](#horaires) qui suivent le soleil, et de l'automatisation solaire ([ombrage](#ombrage-automatique), [héliotropie](#héliotropie)) aux volets que vous avez déjà, le tout configuré depuis un [panneau d'administration](#le-panneau-dadministration) avec une matrice modes × volets, en français ou en anglais.

[![Ouvrir ce dépôt dans HACS sur votre Home Assistant.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Pulpyyyy&repository=cover-extender&category=integration)

![Onglet Matrice](https://raw.githubusercontent.com/Pulpyyyy/cover-extender/main/docs/panel-matrix.png)

---

## Philosophie

Cover Extender repose sur une idée simple : **l'automatisation doit renforcer le contrôle, pas le remplacer**.

### 🎯 L'intention d'abord, la mécanique ensuite

Les automatisations classiques lient souvent **des conditions directement à des actions** :

> *Si l'élévation du soleil > X → mettre le volet à Y*

Efficace, mais cette approche devient vite difficile à comprendre, à contourner ou à déboguer.

Cover Extender prend un autre chemin :

- Vous exprimez une **intention** avec des **modes**
- Chaque mode définit un *contexte* (verrou, comportement, stratégie)
- La logique d'automatisation ne tourne **que lorsqu'elle est explicitement autorisée**

Un mode répond à la question :

> *« Que doit faire ce volet en ce moment ? »*

Et non :

> *« Quelle automatisation s'est déclenchée ? »*

### 🧩 Non destructif par conception

Cover Extender suit une règle stricte :

> **Il ne remplace, ne clone et ne s'approprie jamais vos volets.**

Plutôt que de cacher votre matériel derrière une logique opaque, il **étend ce qui existe déjà** : vos entités `cover.*` restent la seule source de vérité, et l'intégration ajoute de l'intelligence *autour* d'elles, jamais *par-dessus*. Il :

- ajoute des attributs
- crée des entités d'assistance (sélecteurs, interrupteurs, capteurs)
- orchestre les commandes à travers une couche maîtrisée

À tout moment :

- Vous pouvez contourner Cover Extender et piloter le volet à la main
- Un redémarrage ou un rechargement ne corrompt jamais l'état natif du volet
- Supprimer l'intégration rend un système propre

Votre matériel reste autonome. Cover Extender est une intelligence optionnelle.

### 🔐 La sécurité avant la surprise

Un mouvement physique non voulu est l'une des frustrations les plus courantes avec les automatisations de volets.

Cover Extender en fait une **préoccupation de premier plan** :

- Le **verrou** retient les commandes passées par Cover Extender et les mémorise à la place
- Les **exclusions de sécurité** (par ex. une fenêtre ouverte) bloquent tout mouvement que Cover Extender ferait
- Les **inhibitions** (par ex. un invité dans la chambre) font de même, sauf pour un mode prioritaire
- Rien ne se rattrape plus tard que vous n'ayez demandé

Si un volet ne bouge pas, ce n'est jamais un mystère :

> *Il est soit verrouillé, soit exclu, soit en attente en mémoire.*

### 🧠 La mémoire plutôt que les suppositions

Quand l'automatisation est en pause, beaucoup de systèmes abandonnent, tout simplement.

Pas Cover Extender.

- Chaque passage à un mode verrouillé mémorise la position actuelle
- Les mouvements bloqués sont mémorisés volontairement
- Le déverrouillage n'applique la mémoire que lorsque le mouvement est sûr

Cela crée une **continuité d'intention** :

> *« Je voulais cette position : applique-la dès que possible. »*

Et non :

> *« L'automatisation a échoué, état perdu. »*

### 🌞 Le soleil comme stratégie, pas comme réflexe

La logique solaire de Cover Extender est **délibérée, pas réactive**.

- Les données solaires sont toujours calculées
- Mais les actions n'ont lieu que lorsque :
  - l'interrupteur d'automatisation correspondant est allumé
  - en général activé par un mode

Aucun processus en arrière-plan ne lutte en permanence contre l'utilisateur. L'automatisation solaire est :

- délimitée
- réversible
- visible

C'est vous qui décidez *quand* le soleil compte.

### 🔍 L'explicite plutôt que l'astucieux

Cover Extender évite volontairement :

- les hypothèses cachées
- les enchaînements de comportements implicites
- les actions « intelligentes » sans déclencheur clair

Il privilégie plutôt :

- des modes explicites
- des interrupteurs visibles
- des changements d'état déterministes
- des événements Home Assistant pour l'orchestration externe

Tout ce qu'il fait est :

- observable
- débogable
- réversible

### 🤝 Un bon citoyen Home Assistant

Cover Extender respecte l'écosystème de Home Assistant :

- Configuration entièrement dans l'interface, via un panneau d'administration intégré
- Rechargement à chaud, sans redémarrage
- Entités, services et événements natifs
- S'intègre aux tableaux de bord et aux automatisations
- Pas de cloud, pas de bidouille par interrogation périodique

Il se veut :

> *« Ce que Home Assistant aurait pu livrer, si les volets connaissaient les modes. »*

### ✅ En une phrase

**Cover Extender n'automatise pas vos volets à votre place : il vous donne les outils pour exprimer une intention, en toute sécurité, de façon prévisible, et selon vos propres règles.**

---

## Installation

Nécessite **Home Assistant 2026.1** ou plus récent, et des volets qui acceptent une position (de 0 à 100).

### Avec HACS (recommandé)

Cover Extender n'est pas encore dans la liste par défaut de HACS : ajoutez-le comme dépôt personnalisé.

[![Ouvrir ce dépôt dans HACS sur votre Home Assistant.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Pulpyyyy&repository=cover-extender&category=integration)

Ou à la main :

1. Dans Home Assistant, ouvrez **HACS**, puis le menu **⋮** (en haut à droite) et **Dépôts personnalisés**.
2. Dépôt : `https://github.com/Pulpyyyy/cover-extender`, type : **Intégration**, puis **Ajouter**.
3. Cherchez **Cover Extender** dans HACS, ouvrez-le et cliquez sur **Télécharger**.
4. **Redémarrez** Home Assistant.

### Manuellement

1. Téléchargez la dernière [version](https://github.com/Pulpyyyy/cover-extender/releases).
2. Copiez le dossier `custom_components/cover_extender/` dans le dossier `custom_components/` de votre configuration Home Assistant (créez-le au besoin).
3. **Redémarrez** Home Assistant.

### Ajouter l'intégration

[![Ajouter Cover Extender à votre Home Assistant.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=cover_extender)

Ou **Paramètres → Appareils et services → Ajouter une intégration**, puis cherchez **Cover Extender**. Il n'y a rien à remplir : l'intégration est créée et tout le reste se passe dans le panneau.

**Mise à jour depuis la 2.x :** la configuration est migrée automatiquement au premier démarrage. La migration est à sens unique : revenir en 2.x ensuite est refusé plutôt que de risquer de corrompre la configuration.

**Mise à jour depuis la 3.x :** la 4.0 renomme les entités qu'elle crée en `<volet>_cx_<fonction>` (par exemple `switch.salon_lock` devient `switch.salon_cx_lock`, et `select.mode_salon` devient `select.salon_cx_mode`). Home Assistant conserve leur historique mais ne met pas à jour vos automatisations, scripts et tableaux de bord : **Paramètres → Réparations** liste chaque ancien et nouvel identifiant pour que vous puissiez les remplacer. Un identifiant que vous aviez renommé vous-même est laissé tel quel. Les entités sont rattachées à l'appareil du volet (à l'appareil **Cover Extender** quand le volet n'en a pas), et leurs noms restent en anglais (`CX lock`, `CX mode`...), identiques dans toutes les langues.

---

## Prise en main

Ce parcours configure un volet avec deux modes, *Jour* (ouvert) et *Nuit* (fermé). Comptez cinq minutes.

1. **Ouvrez le panneau.** Cliquez sur **Cover Extender** dans la barre latérale, ou sur le bouton de la page de l'intégration, ou allez sur `http://<votre-ha>:8123/cover-extender`.
2. **Créez une façade.** Dans **Maison → Façades**, cliquez sur **Ajouter une façade**. Nommez-la (par ex. *Sud*) et réglez son **azimut**, la direction vers laquelle regardent les fenêtres : 0° = nord, 90° = est, 180° = sud, 270° = ouest. Une application boussole posée à plat contre la fenêtre, en regardant dehors, donne la valeur. Dans le panneau, tapez-la, choisissez l'une des huit directions, ou faites glisser la flèche sur la boussole.
3. **Créez deux modes.** Dans **Modes**, cliquez deux fois sur **Ajouter un mode** : *Jour* et *Nuit*. Laissez **Position des volets** sur *Fixe* pour les deux. Activez **Verrouiller les volets** sur *Nuit* si vous voulez que les commandes passées par Cover Extender attendent le matin.
4. **Ajoutez votre volet.** Dans **Volets**, cliquez sur **Ajouter un volet**, choisissez l'entité `cover.*` et la façade *Sud*, puis **Enregistrer**.
5. **Réglez les positions.** Dans **Matrice**, cliquez sur la cellule vide *Jour* de votre volet : cela ajoute le mode au volet. Choisissez **Fixe** et 100 %. Faites de même pour *Nuit* à 0 %, puis **Enregistrer**. Les positions suivent la convention de Home Assistant : **0 = fermé, 100 = ouvert**.
6. **Essayez.** Une nouvelle entité `select.<votre_volet>_cx_mode` est apparue. Passez-la de *Jour* à *Nuit* : le volet se ferme.

### Ensuite

- Ouvrez et fermez à la bonne heure avec les [horaires](#horaires) : une heure du matin et du soir qui suivent le soleil, et un mode ou une position par volet.
- Ou changez de mode depuis vos propres automatisations avec l'action `cover_extender.apply_mode`, par exemple *Nuit* au coucher du soleil :

  ```yaml
  triggers:
    - trigger: sun
      event: sunset
  actions:
    - action: cover_extender.apply_mode
      target:
        area_id: salon
      data:
        mode: Nuit
  ```

- Ajoutez une [entité d'exclusion](#exclusions) (un contact de fenêtre) pour que le volet ne se ferme jamais sur une fenêtre ouverte.
- Essayez l'[ombrage](#ombrage-automatique) : créez un mode avec le comportement *Ombrage* et remplissez les sections **Géométrie** et **Ombrage** du volet.
- Utilisez le [sélecteur global](#le-sélecteur-global) pour changer tous les volets d'un coup depuis un tableau de bord.

---

## Les notions

### Modes

Un mode dit *ce que le volet doit faire en ce moment*. Chaque mode a un nom, une icône et une couleur, et en option :

- **Verrouiller les volets** : tant que le mode est actif, le volet est [verrouillé](#verrou-et-mémoire).
- **Position des volets** : *Fixe* (chaque volet reçoit sa position depuis la matrice), *Ombrage* (la position est calculée d'après le soleil) ou *Héliotropie*.
- **Mode prioritaire** : le mode passe outre les [inhibitions](#exclusions) (jamais les exclusions de sécurité). Typiquement un mode *Alarme* qui doit fermer tous les volets, chambre d'amis comprise.
- **Durée limitée** : le mode ne dure qu'un temps (de 1 minute à 24 heures), c'est un [mode minuté](#modes-minutés).
- **Masquer du sélecteur** : le mode reste utilisable par les automatisations mais n'apparaît pas dans le sélecteur global.

Un mode ne s'applique qu'aux volets auxquels il est lié (une cellule de la matrice). Pour chaque volet lié, la matrice règle ce qui se passe quand le mode s'active :

| Choix | Effet |
|---|---|
| **Fixe** | Le volet va à cette position (0-100). |
| **Entité** | Le volet suit la valeur d'une entité `input_number` ou `number`, en direct, tant que le mode est actif. |
| **Aucune** | Le volet ne bouge pas. Si le mode précédent était verrouillé et pas celui-ci, la position mémorisée est restaurée. |
| **Auto** (modes à comportement) | La position est calculée. Choisir Fixe ou Entité à la place surcharge le calcul pour ce volet seulement. |

Chaque volet reçoit une entité `select.<volet>_cx_mode` qui liste ses modes liés : la changer applique le mode.

### Verrou et mémoire

Le verrou est un interrupteur par volet, `switch.<volet>_cx_lock`. Les modes l'allument et l'éteignent, et vous pouvez le basculer à la main.

Tant qu'il est allumé, **les positions demandées via Cover Extender sont mémorisées au lieu de bouger le volet** : les actions `set_cover_position`, `open_cover` et `close_cover` de Cover Extender, et les positions Entité du mode actif.

- Passer d'un mode non verrouillé à un mode verrouillé **mémorise la position actuelle**.
- Revenir à un mode non verrouillé sans position (Aucune) **restaure** cette position.
- Éteindre le verrou à la main **applique la mémoire** (sauf si une exclusion est active).
- La position mémorisée apparaît dans l'attribut `memory` du volet.

> [!IMPORTANT]
> Le verrou ne filtre que ce qui passe par Cover Extender. Une télécommande, la carte du volet ou un `cover.set_cover_position` natif font toujours bouger le volet. C'est voulu : Cover Extender ne vous retire jamais la main sur vos volets.

Un mode *Ombrage* ou *Héliotropie* verrouille toujours le volet, pour que ses mouvements calculés n'effacent pas la position que vous aviez avant. Seule exception : un volet qui surcharge le mode avec sa propre position Fixe ou Entité suit le réglage de verrou du mode.

### Horaires

L'onglet **Horaires** contient l'**ouverture du matin** et la **fermeture du soir** de la maison, chacune activable. À chacune, chaque volet applique l'action choisie pour lui dans le tableau sous le graphique : un **mode**, une **position fixe**, ou *Aucune* (le volet ne fait rien). Le tableau est groupé par façade ; sa ligne *Tous les volets* règle d'un coup tous les volets qui proposent l'action choisie, et un volet qui fait autre chose que les autres est mis en évidence.

- Un **mode** est un changement de mode comme un autre : le verrou, les exclusions, les inhibitions, les modes minutés et [qui remplace qui](#qui-remplace-qui) s'appliquent.
- Une **position** (0 à 100 %) déplace le volet sans changer son mode. Au choix, elle :
  - **respecte le verrou** : un volet libre bouge ; un volet verrouillé ne bouge pas, la position part dans sa [mémoire](#verrou-et-mémoire) et il la prend en quittant le mode verrouillé (vers un mode sans position fixe). Une inhibition la retient jusqu'à sa fin.
  - ou **force** : le volet bouge tout de suite, même verrouillé, et passe outre les inhibitions. Le mode et le verrou restent ; la mémoire prend aussi la position, pour que la sortie du mode verrouillé ne l'annule pas. Sur un volet en mode ombrage ou héliotropie, le calcul suivant peut le rebouger (le panneau le signale) ; pour un état qui dure toute la soirée, un mode reste le bon outil.

  Une fenêtre ouverte (exclusion de sécurité) retient les deux : la position est appliquée à sa fermeture.

Chaque heure suit le soleil sur l'année, dans des bornes que vous fixez :

- **Heure max / heure min** : l'heure le jour où le soleil se lève ou se couche le plus tard, et le plus tôt. Entre les deux, la courbe suit le soleil. Collez les deux poignées pour une **heure fixe** toute l'année.
- **Croisement de printemps / d'automne** (optionnel) : la courbe tombe pile sur le lever ou le coucher ce jour-là.
- **Plancher (« pas avant ») / plafond (« pas après »)** : des heures légales que l'horaire ne dépasse jamais, quoi que fasse le soleil.

Le graphique montre le soleil, la courbe, l'heure du jour et les jours où le volet se ferme avant le coucher (ou s'ouvre avant le lever). Chaque réglage est un champ et une poignée à faire glisser.

Si Home Assistant était arrêté à l'heure d'un horaire, le dernier de la journée est appliqué au démarrage (jamais au tout premier démarrage). Trois entités suivent les horaires, sur l'appareil Cover Extender :

| Entité | Contenu |
|---|---|
| `binary_sensor.cx_day` | Allumé entre l'ouverture et la fermeture du jour. Attributs `opening`, `closing`, `next_change`, et `cause` : `time` quand l'heure a atteint un horaire, `setting` quand un horaire a été modifié (une automatisation peut ignorer ce cas). |
| `sensor.cx_morning_opening` | L'ouverture du matin du jour (horodatage). |
| `sensor.cx_evening_closing` | La fermeture du soir du jour (horodatage). |

### Modes minutés

Un mode avec une durée est une parenthèse par-dessus le **mode de base** du volet, le dernier mode sans durée dans lequel il a été mis. Typiquement un mode *Manuel* d'une heure : vous reprenez la main, et le volet revient ensuite à ce qu'il faisait.

| Ce qui se passe | Mode du volet | Mode de base |
|---|---|---|
| L'automatisation du matin applique *Jour* | Jour | **Jour** |
| Vous choisissez *Manuel* (1 h) | Manuel | Jour |
| Avant la fin de l'heure, vous choisissez *Invité* (12 h) | Invité | Jour |
| Fin du délai d'Invité | Jour | Jour |
| L'automatisation du soir applique *Nuit* | Nuit | **Nuit** |

- **À la fin du délai**, le volet revient à son mode de base (« revenir au mode précédent » dans l'éditeur du mode), ou à un mode fixe réglé dans cet éditeur (*Manuel : 1 h, puis Jour*). Le mode fixe ne peut être qu'un mode sans durée : chaque compte à rebours se termine donc sur un mode qui n'en relance aucun.
- **Un mode sans durée choisi entre-temps** s'applique tout de suite, met fin au compte à rebours et devient le mode de base.
- **Re-choisir le mode minuté en cours** relance son compte à rebours.
- L'action `cover_extender.end_timed_mode` y met fin tout de suite.

Le `select.<volet>_cx_mode` du volet indique quand le compte à rebours se termine et quel mode suit, dans ses attributs `mode_ends_at` et `return_mode`. Le compte à rebours survit à un redémarrage de Home Assistant. Le retour est un changement de mode comme un autre : le verrou, les exclusions et les inhibitions s'appliquent.

### Exclusions

L'éditeur du volet a deux listes d'entités qui retiennent le volet tant que l'une d'elles est à `on`, côte à côte sous **Ce qui bloque le volet** :

- **Exclusions de sécurité** (« Sécurité : rien ne bouge ») : un contact de fenêtre ou de porte (`binary_sensor`), un capteur de pluie. Rien ne bouge, **même pas un mode prioritaire**.
- **Inhibitions** (« Pause : Cover Extender n'y touche pas ») : un `input_boolean` « invité dans la chambre », « enfants couchés », ou un capteur template comme « mercredi matin ». Cover Extender ne touche pas au volet, **sauf pour une demande prioritaire** : un mode avec **Mode prioritaire** activé (sous *Avancé* dans l'éditeur du mode), ou l'action `cover_extender.apply_mode` avec `force: true`.

Tant que l'une d'elles retient le volet :

- un changement de mode ou une action Cover Extender ne bouge pas le volet : sa position **attend, et s'applique dès que plus rien ne le retient**. Refermez la fenêtre et le mode *Nuit* choisi entre-temps ferme le volet ; quand l'invité part, l'ouverture du matin qui attendait s'applique ;
- l'ombrage et l'héliotropie ignorent le volet, et se recalent dès que plus rien ne le retient ;
- éteindre le verrou n'applique pas la mémoire.

Une demande prioritaire qui attend une fenêtre s'applique dès que la fenêtre se ferme, même si une inhibition est encore active ; une demande normale attend aussi la fin de l'inhibition. Seule la dernière demande attend : un nouveau mode la remplace.

Pour tout fermer quand l'alarme est armée, chambre d'amis comprise :

```yaml
action: cover_extender.apply_mode
target:
  entity_id: "{{ states.cover | selectattr('attributes.facade', 'defined') | map(attribute='entity_id') | list }}"
data:
  mode: Nuit
  force: true
``` Si le volet a été verrouillé entre-temps, la position d'une action reste en mémoire jusqu'au déverrouillage, comme toute commande passée sous verrou. Une position en attente ne survit pas à un redémarrage de Home Assistant.

### Façades et orientation

Une **façade** est l'orientation d'un mur, partagée par tous les volets de ce mur. Son **azimut** est la direction vers laquelle regardent les fenêtres, vu de l'intérieur : 0° = nord, 90° = est, 180° = sud, 270° = ouest.

Chaque volet décide ensuite quand le soleil lui **fait face** avec deux angles, mesurés depuis la direction de la façade en regardant par la fenêtre :

- **Angle à gauche** : vers l'est pour une façade sud ;
- **Angle à droite** : vers l'ouest pour une façade sud.

Le soleil fait face au volet quand son azimut est entre *façade − angle à gauche* et *façade + angle à droite*, et qu'il est au moins 3° au-dessus de l'horizon. Les valeurs par défaut (85° de chaque côté) couvrent presque tout le demi-plan devant le mur ; réduisez-les pour une fenêtre en retrait dans le mur ou masquée par un bâtiment voisin. Ce secteur unique sert à tout : l'attribut `sun_facing` du volet, l'héliotropie et l'ombrage.

#### Fenêtres de toit et puits de lumière

Une façade a aussi une **pente** : l'angle de la vitre avec l'horizontale. Un mur fait 90° (la valeur par défaut, et celle de toute façade créée avant les pentes), une fenêtre dans un toit à 30° fait 30°, un puits de lumière à plat 0°. Elle se règle dans l'éditeur de façade, sous **Pente** : *Mur*, *Toit* (de 10° à 89°) ou *À plat*.

- **Une fenêtre de toit** voit aussi une partie du ciel derrière elle : le soleil touche la vitre dès qu'il est plus haut que la pente (la pente elle-même quand il est juste derrière, moins quand il est sur le côté). Ses deux angles peuvent aller jusqu'à 180° de chaque côté ; à 180° ils ne masquent rien et ne servent plus qu'à une lucarne, une cheminée ou un bâtiment voisin. Les valeurs par défaut restent à 85° : ouvrez-les sur une fenêtre de toit.
- **Un puits de lumière à plat** voit tout le ciel : le soleil le touche dès qu'il est levé, quelle que soit sa direction, et l'azimut ne sert plus.

Sur un mur rien ne change : chaque règle et chaque formule ci-dessous redonne exactement le cas vertical.

### Gabarits

Plusieurs fenêtres de même taille, sur le même type de mur, partagent leur géométrie et leurs réglages d'ombrage. Un **gabarit** porte ces valeurs une seule fois ; chaque volet qui l'utilise en hérite et n'enregistre que ce qu'il change (affiché comme *écarts* dans l'éditeur). Modifier le gabarit met à jour tous les volets qui l'utilisent.

Un gabarit a aussi un **type de fenêtre**, *Mur*, *Toit* ou *À plat*, choisi en haut de son éditeur : le gabarit d'un mur porte des hauteurs, celui d'un toit des longueurs de vitre le long de la pente. Un volet ne peut prendre qu'un gabarit du type de sa façade ; les autres restent dans sa liste, grisés. Un gabarit de toit est dessiné sur le moins pentu des toits de la maison. Les gabarits créés avant la 4.0 sont ceux d'un mur, ou d'un toit (ou à plat) quand tous leurs volets sont déjà sur une telle façade.

### Ombrage automatique

L'ombrage empêche la lumière directe d'aller plus loin dans la pièce que ce que vous avez décidé. Quand le soleil est devant la fenêtre, le volet descend juste ce qu'il faut ; sinon, il va à sa position par défaut.

Il fonctionne quand :

- l'interrupteur **Ombrage** est activé dans l'éditeur du volet (en tête de sa carte Ombrage), ce qui crée `switch.<volet>_cx_auto_shade` ;
- cet interrupteur est allumé, ce que fait un mode au comportement *Ombrage* ;
- aucune exclusion n'est active.

La position est recalculée à chaque mise à jour de `sun.sun` (toutes les quelques minutes en journée). Une commande n'est envoyée que si elle diffère de la position actuelle d'au moins le **seuil de changement**, et si le volet n'a pas bougé (pour quelque raison que ce soit) depuis la **temporisation**, pour qu'un réglage à la main soit respecté un moment.

| Réglage | Défaut | Sens |
|---|---|---|
| Distance du volet | `0.4` m | Jusqu'où la lumière directe peut entrer dans la pièce, mesuré au sol depuis la fenêtre. Plus petit = le volet ferme davantage. |
| Hauteur maxi | `1.8` m | Hauteur du bas du volet complètement ouvert (100 %), en général le haut de la fenêtre. Sur une fenêtre de toit, la longueur de la vitre le long de la pente. |
| Hauteur mini | `0.0` m | Hauteur du bas du volet complètement fermé (0 %) : 0 pour une porte-fenêtre, la hauteur d'allège pour une fenêtre. |
| Hauteur du soleil mini / maxi | `5` / `180` ° | En dehors de cette plage, le volet va à sa position par défaut. Se lit depuis l'horizon devant, par-dessus le zénith (90°) et, sur une fenêtre de toit, de l'autre côté jusqu'au toit : sur un toit à 30°, 120° est un soleil à 60° de haut derrière. 180 = pas de limite ; sur un mur la plage s'arrête à 90. |
| Position quand le soleil tape | `30` % | Puits de lumière à plat seulement, à la place de la géométrie : la position tant que le soleil touche la vitre. |
| Position mini | `15` % | L'ombrage ne ferme jamais plus que ça. |
| Position par défaut | `100` % | Position quand le soleil n'est pas devant la fenêtre. |
| Seuil de changement | `5` % | Les petits changements sont ignorés, pour ménager le moteur. |
| Temporisation | `2` min | Délai minimal depuis le dernier mouvement du volet (quelle qu'en soit la source) avant que l'ombrage le bouge à nouveau. L'entrée dans un mode d'ombrage l'ignore. |

Le volet laisse ouverte une longueur de vitre `distance × sin(α) / cos(i)`, où α est l'élévation du soleil et i l'angle entre le soleil et la perpendiculaire à la vitre, convertie ensuite en pourcentage entre les hauteurs mini et maxi. Sur un mur, c'est la hauteur habituelle du bas du volet, `distance / cos(γ) × tan(α)`, γ étant l'angle entre le soleil et la direction de la façade. Sur une fenêtre de toit, la longueur se mesure le long de la pente et la distance au niveau du bas de la vitre. Un puits de lumière à plat n'a pas de tache de soleil à tenir près d'un mur : il prend sa *position quand le soleil tape*.

### Héliotropie

L'héliotropie est une fonction de **temps froid** : laisser le soleil chauffer la pièce quand il le peut, garder la chaleur sinon.

Elle fonctionne quand l'interrupteur **Héliotropie** est activé dans l'éditeur du volet (ce qui crée `switch.<volet>_cx_auto_solar_gain`), que cet interrupteur est allumé (un mode au comportement *Héliotropie* s'en charge) et qu'aucune exclusion n'est active. Alors :

- si l'entité de température est au-dessus ou égale au seuil, **rien ne se passe** (le volet reste où il est) ;
- sinon, si le soleil fait face au volet et que la météo est dans la liste des bonnes conditions, le volet va à la **Position au soleil** (100 % par défaut) ;
- sinon il va à la **Position au froid** (0 % par défaut).

L'entité de température, le seuil et l'entité météo sont communs à tous les volets (onglet **Réglages**). Sans entité de température, le test de température est ignoré ; sans entité météo, la météo est considérée comme bonne. Le seuil est un nombre, ou un `input_number` pour le changer depuis un tableau de bord.

### Le sélecteur global

`select.cx_modes` liste tous les modes non masqués, avec leur icône et leur couleur. **Choisir un mode dessus l'applique à tous les volets**, depuis un tableau de bord ou une automatisation (`select.select_option`), en suivant les deux règles ci-dessous. Il n'y a plus d'automatisation à prévoir pour le relier : si vous aviez celle que proposaient les versions précédentes de ce guide, supprimez-la.

### Qui remplace qui

Une demande groupée (le sélecteur global, un [horaire](#horaires) ou l'action `cover_extender.apply_mode`) applique un mode à plusieurs volets d'un coup. Deux réglages de chaque mode la façonnent, sous **Lancé pour plusieurs volets** dans l'éditeur du mode :

- **Ne pas déranger les volets déjà en mode** : les modes qu'il laisse tranquilles. Un volet déjà dans l'un d'eux le garde. Un volet en [mode minuté](#modes-minutés) le garde aussi, et prend le mode demandé à la fin du délai.
- **Volets qui n'ont pas ce mode dans la matrice** : un *mode de repli* appliqué à la place, aux volets auxquels le mode demandé n'est pas lié (ou *Ne rien faire*).

Par exemple :

| Appliquer… | laisse tranquilles les volets en… |
|---|---|
| *Automatique* | *Invités*, *Absence*, *Sieste*, *TV*, *Climatisation* |
| *Nuit* | *Absence*, *Invités*, *Climatisation* |
| *Ombre* | *Invités*, *TV*, *Sieste*, *Manuel*, *Climatisation* |

avec *Absence* qui se replie sur *Automatique* pour les volets auxquels il n'est pas lié. *Nuit* ferme alors la chambre pendant une sieste, mais pas la chambre d'amis ; *Ombre* fonctionne pendant une absence ; et choisir *Absence* sur le sélecteur global met en *Automatique* les volets qui n'ont pas de position *Absence*.

Un choix fait sur le sélecteur d'un volet s'applique toujours, tout comme `apply_mode` avec `force: true` : ces deux réglages ne régissent que les demandes groupées.

---

## Le panneau d'administration

Toute la configuration se fait dans le panneau, à `/cover-extender`. Chaque valeur est vérifiée par le serveur avant d'être enregistrée. Le panneau suit le thème de Home Assistant, et chaque administrateur le lit dans sa langue (français ou anglais).

Les quatre onglets de gauche servent au quotidien, dans l'ordre du travail ; les deux après le trait se règlent une fois. Le panneau s'ouvre sur **Volets**.

| Onglet | Ce qu'il règle |
|---|---|
| **Volets** | Les volets, groupés par façade comme dans la matrice. Chaque carte montre ce que fait le volet en ce moment : son mode et sa position (dessinée et écrite), puis ce qui le retient (un [mode minuté](#modes-minutés) et son heure de fin, le verrou et la position mémorisée, une exclusion ou une inhibition active). Un volet qui suit un [horaire](#horaires) montre ses actions du matin et du soir sur une ligne avec les heures du jour, la prochaine dans la couleur d'accent, et une ligne quand son état change cette prochaine action (verrouillé : la position ira en mémoire ; fenêtre ouverte : il attend) ; un clic sur cette ligne ouvre l'onglet Horaires. En bas, seulement ce qui est actif : ombrage, héliotropie, et les écarts à son gabarit. L'éditeur du volet réunit son entité, sa façade et son gabarit, sa ligne de la matrice (la position de chaque mode, changée avec la fenêtre de la matrice et enregistrée avec le volet), ses horaires, ses [exclusions de sécurité et inhibitions](#exclusions), puis la géométrie, l'ombrage et l'héliotropie, chaque réglage avec une ligne d'explication et un schéma de la fenêtre. Une barre en haut mène à chaque section et marque celles qui ont des écarts. |
| **Modes** | Les modes, une ligne chacun dans l'ordre des sélecteurs de mode : glissez une ligne pour réordonner. Chaque ligne dit comment le mode place les volets et à combien il est lié, et montre son verrou, sa durée, sa priorité, les modes qu'il épargne, son repli, sa visibilité. L'éditeur se lit de haut en bas : icône, couleur, comment il place les volets, verrou et [durée](#modes-minutés), puis **Appliqué à plusieurs volets** en deux phrases à compléter : les modes qu'il laisse tranquilles, et le mode que prennent les volets qui ne l'ont pas (voir [qui remplace qui](#qui-remplace-qui)). |
| **Matrice** | Modes × volets : ajouter les modes aux volets et régler chaque position par volet depuis une seule grille. Un en-tête ouvre son mode. Une cellule *auto* d'un mode d'ombrage ou d'héliotropie peut être remplacée par une position fixe pour ce seul volet (contour ambre). Sur un téléphone, la matrice montre les volets l'un sous l'autre, leurs modes deux par deux, le tableau restant à portée. |
| **Horaires** | L'[ouverture du matin et la fermeture du soir](#horaires) : d'abord une carte pour chacune avec son interrupteur, l'heure du jour et ce qu'elle fait aux volets, puis l'action du matin et du soir de chaque volet, puis la courbe sur l'année de celle choisie en haut. |
| **Maison** | Les façades (orientation réglée sur une boussole, et pente) et les gabarits, deux listes dont chaque ligne ouvre son éditeur. Un gabarit nomme les façades de son type de fenêtre. |
| **Réglages** | L'héliotropie (écrite comme sa règle : il fait frais quand cette température est sous ce seuil, beau quand cette météo annonce ces conditions), la pause entre deux volets, les entités en plus pour chaque volet, et la liste des entités que la configuration a créées. |

Une page qui a quelque chose à enregistrer montre une barre d'enregistrement collée au bas de l'écran, et son onglet porte un point ; sans rien à enregistrer, pas de barre.

### En images

L'éditeur de volet : ce qui bloque le volet, puis le calcul en quatre cartes. Sous son gabarit, *Distance* et *Position mini* sont des écarts de ce volet (ambre, avec la valeur du gabarit et le moyen d'y revenir), le reste est hérité. Les captures sont en anglais ; le panneau suit la langue de chaque administrateur.

![Éditeur de volet](https://raw.githubusercontent.com/Pulpyyyy/cover-extender/main/docs/panel-cover-editor.png)

| L'éditeur de mode | L'onglet Horaires |
|---|---|
| ![Éditeur de mode](https://raw.githubusercontent.com/Pulpyyyy/cover-extender/main/docs/panel-mode-editor.png) | ![Onglet Horaires](https://raw.githubusercontent.com/Pulpyyyy/cover-extender/main/docs/panel-schedules.png) |

| | |
|---|---|
| ![Onglet Volets](https://raw.githubusercontent.com/Pulpyyyy/cover-extender/main/docs/panel-covers.png) | ![Onglet Modes](https://raw.githubusercontent.com/Pulpyyyy/cover-extender/main/docs/panel-modes.png) |

| | |
|---|---|
| ![Onglet Maison](https://raw.githubusercontent.com/Pulpyyyy/cover-extender/main/docs/panel-house.png) | ![Onglet Réglages](https://raw.githubusercontent.com/Pulpyyyy/cover-extender/main/docs/panel-settings.png) |

## Questions fréquentes

**Mon volet ne bouge pas.** La carte du volet dans l'onglet **Volets** dit pourquoi. C'est l'une de ces raisons : le volet est **verrouillé** (`switch.<volet>_cx_lock` est allumé, la position demandée est dans l'attribut `memory`), une **exclusion de sécurité** ou une **inhibition** est à `on`, ou le mode n'a **pas de position** pour ce volet (Aucune, ou le mode n'est pas lié au volet dans la matrice). Pour l'ombrage, vérifiez aussi le seuil de changement et la temporisation.

**J'ai bougé mon volet à la main et il est revenu tout seul.** L'ombrage ou l'héliotropie est actif. L'ombrage attend la temporisation après tout mouvement, puis reprend. Pour garder votre position, passez à un mode sans comportement, ou éteignez `switch.<volet>_cx_auto_shade`.

**Mon volet a changé de mode tout seul.** Un [mode minuté](#modes-minutés) s'est terminé (le volet est revenu à son mode de base, ou au mode de retour fixe du mode), ou un [horaire](#horaires) a appliqué son mode du matin ou du soir. Les événements `cover_extender_timed_mode_ended` et `cover_extender_mode_changed`, et le journal de `select.<volet>_cx_mode`, disent lequel.

**Un volet n'a pas suivi le sélecteur global (ou un `apply_mode` sur plusieurs volets).** Il était dans un mode que le mode demandé laisse tranquille, ou le mode ne lui est pas lié et n'a pas de mode de repli : voir [qui remplace qui](#qui-remplace-qui). `apply_mode` renvoie la raison pour chaque volet dans `reasons` (`spared`, `not_linked`).

**Je ne trouve pas le panneau.** Ouvrez directement `http://<votre-ha>:8123/cover-extender`. Il faut un compte administrateur. Si l'entrée manque dans la barre latérale, elle est peut-être masquée : ouvrez votre **Profil** et modifiez les éléments de la barre latérale.

**`switch.<volet>_cx_auto_shade` n'existe pas.** Activez l'interrupteur **Ombrage** en tête de la carte Ombrage du volet : il appartient au volet, un gabarit n'en a pas. Pareil pour l'héliotropie.

**En ombrage, le volet ferme trop / pas assez.** Augmentez la **Distance du volet** pour laisser entrer plus de soleil, montez la **Position mini** pour garder de la lumière. Après chaque changement, l'action `cover_extender.compute_shade_position` (dans **Outils de développement → Actions**) montre la nouvelle position sans bouger le volet.

**Comment obtenir des journaux de débogage ?** Utilisez **Activer la journalisation de débogage** sur la page de l'intégration, ou ajoutez ceci à `configuration.yaml` puis redémarrez :

```yaml
logger:
  logs:
    custom_components.cover_extender: debug
```

Chaque décision (verrou, exclusion, inhibition, priorité, seuil, temporisation, mode minuté, horaire) est journalisée avec sa raison.

---

## Désinstaller

1. **Paramètres → Appareils et services → Cover Extender → ⋮ → Supprimer.** Les entités créées, les attributs ajoutés et la mémoire enregistrée sont supprimés. Vos volets ne sont pas touchés.
2. Retirez l'intégration de HACS (ou supprimez `custom_components/cover_extender/`), puis redémarrez Home Assistant.

---

## Aide et contributions

- Bugs et demandes : [issues GitHub](https://github.com/Pulpyyyy/cover-extender/issues) (en français ou en anglais). Indiquez vos versions de Home Assistant et de Cover Extender, et joignez les journaux de débogage.
- Les nouveautés de chaque version : [CHANGELOG](CHANGELOG.md) (en anglais).
