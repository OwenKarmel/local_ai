// game.js — Phaser runtime. Builds a level from JSON and runs it.
// Public API (window.Callout): loadLevel(levelJson), applyPatch(ops, levelJson, label, stage), goToStage(i), log(msg, kind),
//   setAppearance(id, {sprite, tint}), setPlayerLook({sprite, tint}), debugProjectile(sprite, tint), .level, .scene, .stage
// Visual-only looks (entity.look, level.player_look, level.scene, level.reactions) are drawn by looks.js (window.LOOKS).
// Levels are played as stages in order (backend /api/stage); reaching an unlocked goal moves on to the next stage.
// Sprites and effects come from sprites.js (window.SPRITES); see assets/catalog.json.
(function () {
  const TILE = 32;
  const COYOTE_MS = 100;     // jump grace after leaving a ledge
  const JUMP_BUFFER_MS = 100; // jump pressed slightly before landing still counts
  const PLAYER_W = 24, PLAYER_H = 30, ENEMY_W = 28, ENEMY_H = 24; // physics bodies (world px); art is skinned around them
  // "grow" scales the player and physics body uniformly; this fits through a 2-tile opening.
  const BIG_SCALE = 1.6, BIG_W = PLAYER_W * BIG_SCALE, BIG_H = PLAYER_H * BIG_SCALE;
  const HURT_GRACE_MS = 1500; // after a big player is hit and shrinks: can't be hurt again for this long
  const S = window.SPRITES;
  const LK = window.LOOKS;
  let currentLevel = null;
  let playerLook = {}; // { sprite?, tint? }; survives restarts
  let stage = { index: 0, count: 1, names: [] }; // which level of the sequence is loaded (GET /api/stage)

  // ---------- side panel log ----------
  function log(msg, kind = "info") {
    const el = document.getElementById("log");
    if (!el) return;
    const div = document.createElement("div");
    div.className = "entry " + kind;
    div.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
    el.prepend(div);
  }
  window.addEventListener("error", (e) => {
    log(`JS error: ${e.message}`, "error");
    reportMechanicsError(null, "callback", e.error || e.message);
  });

  // ---------- sandbox for model-written abilities (mechanics.js) ----------
  window.MECHANICS_ERRORS = [];
  function reportMechanicsError(name, phase, err) {
    const message = String((err && err.message) || err);
    const ab = name && window.ABILITIES && window.ABILITIES[name];
    if (ab) ab.disabled = true;
    const rec = { ability: name, phase, message, stack: err && err.stack ? String(err.stack).split("\n").slice(0, 4).join("\n") : null, t: Date.now() };
    window.MECHANICS_ERRORS.push(rec);
    if (name) log(`Ability "${name}" failed in ${phase}: ${message} (disabled)`, "error");
    window.dispatchEvent(new CustomEvent("mechanics-error", { detail: rec }));
  }

  // ---------- fallback textures (drawn in code; used only when a sprite is missing) ----------
  function makeTextures(scene) {
    if (scene.textures.exists("player")) return;
    const g = scene.make.graphics({ add: false });
    const tex = (key, w, h, draw) => { g.clear(); draw(g); g.generateTexture(key, w, h); };
    tex("player", PLAYER_W, PLAYER_H, (g) => g.fillStyle(0xe74c3c).fillRect(0, 0, PLAYER_W, PLAYER_H));
    tex("player_big", BIG_W, BIG_H, (g) => g.fillStyle(0xf39c12).fillRect(0, 0, BIG_W, BIG_H));
    tex("enemy", ENEMY_W, ENEMY_H, (g) => g.fillStyle(0x8e5a2b).fillRect(0, 0, ENEMY_W, ENEMY_H));
    tex("platform", TILE, TILE, (g) => { g.fillStyle(0x6b4a2b).fillRect(0, 0, TILE, TILE); g.lineStyle(2, 0x553a20).strokeRect(1, 1, TILE - 2, TILE - 2); });
    tex("spikes", TILE, TILE, (g) => g.fillStyle(0xbdc3c7).fillRect(0, TILE / 2, TILE, TILE / 2));
    tex("lava", TILE, TILE, (g) => g.fillStyle(0xe67e22).fillRect(0, 0, TILE, TILE));
    tex("coin", 16, 16, (g) => g.fillStyle(0xf1c40f).fillRect(0, 0, 16, 16));
    tex("double_jump", 22, 22, (g) => g.fillStyle(0x3498db).fillRect(0, 0, 22, 22));
    tex("grow", 22, 22, (g) => g.fillStyle(0xe03c3c).fillRect(0, 0, 22, 22));
    tex("goal", TILE, TILE * 2, (g) => g.fillStyle(0x9b59b6).fillRect(0, 0, TILE, TILE * 2));
    tex("fx_dot", 8, 8, (g) => g.fillStyle(0xffffff).fillCircle(4, 4, 4));
    tex("fx_ball", 14, 14, (g) => g.fillStyle(0xffffff).fillCircle(7, 7, 7));
    g.destroy();
  }

  // ---------- scene ----------
  class GameScene extends Phaser.Scene {
    constructor() { super("game"); this.TILE = TILE; }

    preload() { S.preload(this); }

    create() {
      const L = currentLevel;
      this.level = L;
      this.dead = false;
      this.won = false;
      this.coins = 0;
      this.totalCoins = L.entities.filter((e) => e.type === "coin").length;
      this.hasDoubleJump = false;
      this.isBig = false;   // "grow" power-up: bigger player that survives one hit
      this.airJumpsUsed = 0;
      this.lastGroundTime = -9999;
      this.jumpedSinceGround = false;
      this.jumpBufferUntil = 0;
      this.graceUntil = 0; // after a live change, hazards/enemies can't kill until this time

      makeTextures(this);
      S.createAnims(this);
      const W = L.width * TILE, H = L.height * TILE;
      this.worldH = H;
      this.physics.world.gravity.y = L.physics.gravity;
      this.physics.world.setBounds(0, 0, W, H);
      this.physics.world.setBoundsCollision(true, true, true, false); // can fall out the bottom
      this.cameras.main.setBounds(0, 0, W, H).setBackgroundColor("#cfefff");
      this.makeBackground();
      S.fx.init(this);
      LK.init(this);
      this.wasOnGround = true;
      this.stepDist = 0;

      this.platforms = this.physics.add.staticGroup();
      this.hazards = this.physics.add.staticGroup();
      this.items = this.physics.add.staticGroup();
      this.enemies = this.physics.add.group();
      this.enemyShots = this.physics.add.group({ allowGravity: false }); // see spawnEnemyShot
      this.hpBars = this.add.graphics().setDepth(8);
      this.lockHintUntil = 0;
      this.behaving = []; // sprites with behaviors
      this.byId = {};     // entity id -> game object

      for (const e of L.entities) this.spawnEntity(e);

      // player: sprite.x/y is the center of its 24x30 body
      const sx = L.spawn.x * TILE + TILE / 2, sy = (L.spawn.y + 1) * TILE - PLAYER_H / 2;
      this.player = this.physics.add.sprite(sx, sy, "player").setDepth(3);
      this.skinPlayer();
      this.player.setCollideWorldBounds(true);
      this.player.body.setMaxVelocityY(1200);

      this.physics.add.collider(this.player, this.platforms);
      this.physics.add.collider(this.enemies, this.platforms);
      this.physics.add.overlap(this.player, this.hazards, () => this.hurt("Ouch! Hazard"));
      this.physics.add.overlap(this.player, this.enemies, (p, en) => this.hitEnemy(p, en));
      this.physics.add.overlap(this.player, this.items, (p, it) => this.collect(it));
      this.physics.add.overlap(this.player, this.enemyShots, (p, shot) => {
        if (this.dead || this.time.now < this.graceUntil) return;
        S.fx.burst(shot.x, shot.y, shot.trailColor ?? 0xffa030, 6);
        shot.destroy();
        this.hurt("Hit by a projectile");
      });
      this.physics.add.overlap(this.enemyShots, this.platforms, (shot) => { S.fx.burst(shot.x, shot.y, shot.trailColor ?? 0xffa030, 6); shot.destroy(); });

      this.cameras.main.startFollow(this.player, true, 0.15, 0.15);
      this.refreshMotionPlatforms();

      // input
      this.cursors = this.input.keyboard.createCursorKeys();
      this.keys = this.input.keyboard.addKeys("W,A,S,D,R");

      // HUD
      this.hud = this.add.text(10, 8, "", { fontFamily: "monospace", fontSize: "16px", color: "#fff", stroke: "#000", strokeThickness: 3 })
        .setScrollFactor(0).setDepth(10);
      this.banner = this.add.text(480, 200, "", { fontFamily: "monospace", fontSize: "32px", color: "#fff", stroke: "#000", strokeThickness: 5, align: "center" })
        .setOrigin(0.5).setScrollFactor(0).setDepth(10);
      this.toast = this.add.text(480, 44, "", { fontFamily: "monospace", fontSize: "18px", color: "#fff", stroke: "#3a2a6a", strokeThickness: 4 })
        .setOrigin(0.5).setScrollFactor(0).setDepth(10).setAlpha(0);
      this.micIcon = this.add.graphics().setScrollFactor(0).setDepth(12);
      this.micEmoji = this.add.text(0, 0, "🎤", { fontFamily: "Apple Color Emoji, Noto Color Emoji, sans-serif", fontSize: "27px" }).setScrollFactor(0).setDepth(13);
      this.micV = this.add.text(0, 0, "V", { fontFamily: "monospace", fontSize: "12px", color: "#fff", fontStyle: "bold" }).setScrollFactor(0).setDepth(14);
      this.commandBox = this.add.graphics().setScrollFactor(0).setDepth(12).setAlpha(0);
      this.commandText = this.add.text(0, 0, "", { fontFamily: "monospace", fontSize: "12px", color: "#f0f0f0" }).setScrollFactor(0).setDepth(13).setAlpha(0);
      this.drawMicIcon(false);
      LK.applyScene(this, L.scene);
      this.updateHud();
      this.installAbilities();
    }

    // Model-written code arrives as level.abilities[name].code (backend/codegen.py). Register it in ABILITIES
    // (sandboxed: a load error is reported and the ability stays off). Same code twice is a no-op.
    loadAbilityCode(name, a) {
      const cur = window.ABILITIES[name];
      if (!a || !a.code || a.enabled === false) { if (cur && cur.__code) delete window.ABILITIES[name]; return false; }
      if (cur && cur.__code === a.code) return false;
      try {
        const reg = {};
        new Function("ABILITIES", "Phaser", a.code)(reg, Phaser);
        const ab = reg[name] || Object.values(reg)[0];
        if (!ab) throw new Error("the code did not register an ability");
        ab.__code = a.code;
        window.ABILITIES[name] = ab;
        return true;
      } catch (err) {
        reportMechanicsError(name, "load", err);
        return false;
      }
    }

    installAbilities() {
      for (const [name, a] of Object.entries((this.level && this.level.abilities) || {})) this.loadAbilityCode(name, a);
      this.abilityApis = {};
      for (const [name, ab] of Object.entries(window.ABILITIES || {})) {
        if (!ab || ab.disabled) continue;
        const api = (this.abilityApis[name] = window.makeMechanicsApi(this, name, reportMechanicsError));
        if (typeof ab.setup !== "function") continue;
        try { ab.setup(this, api); } catch (err) { reportMechanicsError(name, "setup", err); }
      }
    }

    runAbilities(dt) {
      for (const [name, ab] of Object.entries(window.ABILITIES || {})) {
        if (!ab || ab.disabled || typeof ab.update !== "function") continue;
        try { ab.update(this, dt, this.abilityApis[name]); } catch (err) { reportMechanicsError(name, "update", err); }
      }
    }

    // Parallax sky: clouds band on top, hills band at the bottom (skipped if the art is missing).
    makeBackground() {
      this.bg = [];
      const band = (name, y, factor) => {
        const e = S.catalog[name];
        if (!e || !this.textures.exists(S.key(e.file))) return;
        const ts = this.add.tileSprite(0, y, this.scale.width, e.size[1], S.key(e.file)).setOrigin(0, 0).setScrollFactor(0).setDepth(-10);
        this.bg.push({ ts, factor, isSky: true }); // all three bands have an opaque sky: hidden under a custom sky
      };
      const h = this.scale.height;
      band("bg_sky", 0, 0);
      band("bg_clouds", h - 512 + 56, 0.15);
      band("bg_hills", h - 256 + 56, 0.35);
    }

    // ----- entities -----
    spawnEntity(e) {
      const w = (e.w || 1) * TILE, h = (e.h || 1) * TILE;
      const left = e.x * TILE, top = e.y * TILE, cx = left + w / 2, cy = top + h / 2;
      let obj = null;
      switch (e.type) {
        case "platform":
          obj = this.add.zone(cx, cy, w, h);
          obj.props = e.props || {};
          this.platforms.add(obj);
          break;
        case "spikes":
        case "lava":
          // forgiving hitbox: lower part of the tiles
          obj = this.add.zone(cx, top + h * 0.65, w - 6, h * 0.6);
          this.hazards.add(obj);
          break;
        case "enemy": {
          const { bh } = this.enemyBody(e);
          obj = this.enemies.create(cx, top + h - bh / 2, "enemy").setDepth(2);
          obj.setCollideWorldBounds(true);
          obj.damage = 0; // hits taken; it is defeated when this reaches props.hp (default 1)
          break;
        }
        case "coin":
        case "double_jump":
        case "grow":
        case "goal":
          obj = this.items.create(cx, cy, e.type).setDepth(1);
          break;
        default:
          log(`Unknown entity type '${e.type}' (${e.id})`, "error");
          return;
      }
      obj.def = e;
      obj.props = e.props || {};
      obj.state = {};
      obj.disabledBehaviors = new Set();
      this.byId[e.id] = obj;
      this.skinEntity(obj);
      if (e.behaviors && e.behaviors.length) this.behaving.push(obj);
    }

    // (Re)apply an entity's look from def.sprite / def.tint. Safe to call any time; never throws on bad names.
    skinEntity(obj) {
      const e = obj.def, t = e.type;
      const w = (e.w || 1) * TILE, h = (e.h || 1) * TILE;
      const left = e.x * TILE, top = e.y * TILE, cx = left + w / 2, cy = top + h / 2;
      const entry = S.resolve(this, t, e.sprite);
      let kind = "static";
      if (t === "platform" || t === "spikes" || t === "lava") {
        kind = "area";
        (obj.visuals || []).forEach((v) => v.destroy());
        obj.visuals = S.buildArea(this, entry, t, left, top, e.w || 1, e.h || 1);
      } else if (t === "enemy") {
        kind = "dynamic";
        const { bw, bh, mul, mulY } = this.enemyBody(e);
        if (obj.bodyH && obj.body) obj.y -= (bh - obj.bodyH) / 2; // size changed live: keep its feet on the ground
        S.skinDynamic(this, obj, entry, "enemy", bw, bh, mul, mulY);
        S.play(obj, "walk");
      } else if (t === "coin") {
        S.skinStatic(this, obj, entry, "coin", cx, cy, cx, cy, 16, 16);
        S.play(obj, "spin");
      } else if (t === "double_jump" || t === "grow") {
        S.skinStatic(this, obj, entry, t, cx, cy, cx, cy, 22, 22);
        if (!obj.idleFx && obj.active) obj.idleFx = S.fx.idle(cx, cy);
      } else if (t === "goal") {
        // flag art is 2 tiles tall with the pole on its left edge; hitbox stays the full entity rect
        const artX = entry ? left + (entry.size[0] * (entry.scale || 1)) / 2 + 6 : cx;
        const artY = entry ? top + h - (entry.size[1] * (entry.scale || 1)) / 2 : cy;
        S.skinStatic(this, obj, entry, "goal", artX, artY, cx, cy, w, h);
        S.play(obj, "wave");
      }
      S.applyTint(obj, entry, e.tint, e.look);
      LK.applyObject(this, obj, e.look, kind);
    }

    // Enemy physics body in world px: 28x24 per tile of w/h, so a 2x2 enemy is twice as big. Art scales with it,
    // and so does look.scale / scale_x / scale_y (a bigger-looking enemy is also bigger to hit).
    enemyBody(e) {
      const w = e.w || 1, h = e.h || 1, lk = e.look || {};
      const sx = (lk.scale || 1) * (lk.scale_x || 1), sy = (lk.scale || 1) * (lk.scale_y || 1), m = Math.min(w, h);
      return { bw: ENEMY_W * w * sx, bh: ENEMY_H * h * sy, mul: m * sx, mulY: m * sy };
    }

    // Player look: level.player_look (from commands), overridden by Callout.setPlayerLook (dev tool).
    playerLookNow() {
      const out = { ...((this.level && this.level.player_look) || {}) };
      for (const [k, v] of Object.entries(playerLook)) if (v !== undefined) out[k] = v;
      return out;
    }

    // Small: playerLook.sprite (default "player"), body 24x30. Big: playerLook.bigSprite (default "player_big"), body 28x48.
    // Look size (scale/scale_x/scale_y) only changes the art: the body stays the shared-config size.
    skinPlayer() {
      const p = this.player, big = this.isBig, look = this.playerLookNow();
      // A custom sprite (e.g. "look like a frog") is used while grown too, unless a big sprite was chosen.
      const bigEntry = big ? S.resolve(this, "player_big", look.bigSprite || null) : null;
      const custom = look.sprite ? S.resolve(this, "player", look.sprite) : null;
      const entry = (big && !look.sprite ? bigEntry : null) || custom || S.resolve(this, "player", null);
      const mx = (look.scale || 1) * (look.scale_x || 1), my = (look.scale || 1) * (look.scale_y || 1);
      if (big && entry !== bigEntry) { // no tall art: stretch the normal art to the big body
        S.skinDynamic(this, p, entry, "player", BIG_W, BIG_H, mx * BIG_W / PLAYER_W, my * BIG_H / PLAYER_H);
      } else {
        S.skinDynamic(this, p, entry, big ? "player_big" : "player", big ? BIG_W : PLAYER_W, big ? BIG_H : PLAYER_H, mx, my);
      }
      S.applyTint(p, entry, look.tint);
      LK.applyObject(this, p, look, "dynamic");
      S.play(p, "idle");
    }

    // Grow or shrink the player (look + art + hitbox), keeping the feet where they are. Usable from mechanics.js.
    setPlayerBig(on) {
      on = !!on;
      if (on === this.isBig) return;
      const p = this.player;
      p.y -= ((on ? 1 : -1) * (BIG_H - PLAYER_H)) / 2; // sprite.x/y is the body center: lift so the feet stay put
      this.isBig = on;
      this.skinPlayer();
      S.fx.sparkle(p.x, p.y, on ? 0xffe08a : 0xffffff, 12);
      this.ring(p.x, p.y, on ? 0xffb3b3 : 0xffffff, 8);
      this.updateHud();
    }

    // Hazard or enemy contact. A big player shrinks back and gets a short grace period instead of dying.
    hurt(reason) {
      if (this.dead || this.won || this.time.now < this.graceUntil) return;
      LK.react(this, "hurt", this.player);
      if (!this.isBig) { this.die(reason); return; }
      this.setPlayerBig(false);
      this.graceUntil = this.time.now + HURT_GRACE_MS;
      const p = this.player;
      S.fx.burst(p.x, p.y, 0xffb3b3, 10);
      this.tweens.add({ targets: p, alpha: 0.3, duration: 100, yoyo: true, repeat: Math.floor(HURT_GRACE_MS / 200) - 1,
                        onComplete: () => p.setAlpha(1) });
      log("Hit while big: shrank back", "info");
    }

    // Live look change for one entity (used by live patching for update_entity with sprite/tint).
    setAppearance(id, changes) {
      const obj = this.byId[id];
      if (!obj) { log(`setAppearance: no entity '${id}'`, "error"); return false; }
      if ("sprite" in changes) obj.def.sprite = changes.sprite;
      if ("tint" in changes) obj.def.tint = changes.tint;
      this.skinEntity(obj);
      return true;
    }

    // ----- live patching (O3): apply LowLevelOps to the running scene, no restart -----
    // `next` is the full level after the change; ops say what differs. Player, score and power-ups are untouched.
    applyOps(ops, next, label) {
      const findDef = (id) => next.entities.find((e) => e.id === id);
      let globalChange = false;
      const looks = new Set();
      for (const op of ops) {
        switch (op.op) {
          case "remove_entity": this.liveRemove(op.id, true); break;
          case "add_entity": {
            const def = findDef(op.entity.id) || op.entity;
            this.avoidPlayer(def);
            this.liveAdd(def);
            break;
          }
          case "update_entity": this.liveUpdate(op.id, findDef(op.id)); break;
          case "set_physics": globalChange = true; break;
          case "set_ability": {
            globalChange = true;
            if (this.loadAbilityCode(op.ability, op.settings)) { // new model-written code: start it now
              const ab = window.ABILITIES[op.ability];
              const api = (this.abilityApis[op.ability] = window.makeMechanicsApi(this, op.ability, reportMechanicsError));
              try { if (typeof ab.setup === "function") ab.setup(this, api); } catch (err) { reportMechanicsError(op.ability, "setup", err); }
            }
            break;
          }
          case "set_player_look": case "set_scene": case "set_reactions": looks.add(op.op); break;
          default: log(`Unknown patch op '${op.op}'`, "error");
        }
      }
      this.level = next;
      this.physics.world.gravity.y = next.physics.gravity;
      for (const id in this.byId) { // point every live object at its entity in the new level
        const d = findDef(id);
        if (d) { this.byId[id].def = d; this.byId[id].props = d.props || {}; }
      }
      this.refreshMotionPlatforms();
      if (looks.has("set_player_look")) { this.skinPlayer(); this.ring(this.player.x, this.player.y, 0xfff2a0, 8); }
      if (looks.has("set_scene")) LK.applyScene(this, next.scene);
      this.graceUntil = this.time.now + 700; // don't let a change kill the player on the spot
      if (globalChange) this.globalPulse();
      if (label) this.showToast(label);
      this.updateHud();
    }

    liveAdd(def) {
      this.spawnEntity(def);
      const obj = this.byId[def.id];
      if (!obj) return;
      if (def.type === "coin") this.totalCoins++;
      this.popIn(obj);
    }

    liveRemove(id, animate) {
      const obj = this.byId[id];
      if (!obj) return;
      const wasActive = obj.active;
      delete this.byId[id];
      this.behaving = this.behaving.filter((o) => o !== obj);
      if (obj.def.type === "coin" && wasActive) this.totalCoins--;
      if (obj.idleFx) { obj.idleFx.destroy(); obj.idleFx = null; }
      const visuals = obj.visuals || [];
      const isZone = obj.type === "Zone";
      if (isZone) obj.destroy(); // platform/hazard: collision goes away immediately, art fades out
      else if (obj.body) obj.disableBody(false, false);
      const targets = isZone ? visuals : [obj];
      if (!animate || !wasActive) { targets.forEach((t) => t.destroy()); return; }
      const { cx, cy } = this.defCenter(obj.def);
      S.fx.burst(cx, cy, 0xffffff, 10);
      this.tweens.add({
        targets, alpha: 0, duration: 260, ease: "Quad.easeIn",
        ...(isZone ? { y: "+=12" } : { scaleX: 0, scaleY: 0 }),
        onComplete: () => targets.forEach((t) => t.destroy()),
      });
    }

    liveUpdate(id, def) {
      const obj = this.byId[id];
      if (!def) return;
      if (!obj) { this.liveAdd(def); return; }
      if (!obj.active && obj.type !== "Zone") { obj.def = def; obj.props = def.props || {}; return; } // collected/stomped: stays gone
      const old = obj.def;
      const moved = ["type", "x", "y", "w", "h"].some((k) => (old[k] ?? 1) !== (def[k] ?? 1));
      if (moved) { // geometry changed: crossfade old art out, new entity in (enemies keep the hits they took)
        const damage = obj.damage;
        this.liveRemove(id, true);
        this.liveAdd(def);
        if (damage && this.byId[id]) this.byId[id].damage = damage;
        return;
      }
      obj.def = def;
      obj.props = def.props || {};
      obj.disabledBehaviors.clear();
      const behaves = def.behaviors && def.behaviors.length;
      if (behaves && !this.behaving.includes(obj)) this.behaving.push(obj);
      if (!behaves) this.behaving = this.behaving.filter((o) => o !== obj);
      if (old.sprite !== def.sprite || old.tint !== def.tint || JSON.stringify(old.look) !== JSON.stringify(def.look)) this.skinEntity(obj);
      this.pulse(obj);
      if (def.type === "enemy" && this.enemyHp(obj) <= 0) this.defeatEnemy(obj); // hp lowered below the hits taken
    }

    // Contract: never spawn anything on top of the player; slide it away tile by tile (x only).
    avoidPlayer(def) {
      const p = this.player.body, T = TILE, w = def.w || 1, h = def.h || 1;
      const hits = (x) => x * T < p.right + T / 2 && (x + w) * T > p.left - T / 2 && def.y * T < p.bottom && (def.y + h) * T > p.top;
      if (!hits(def.x)) return;
      const dir = (def.x + w / 2) * T >= p.center.x ? 1 : -1;
      for (let step = 1; step < this.level.width; step++) {
        for (const d of [dir, -dir]) {
          const x = def.x + d * step;
          if (x >= 0 && x + w <= this.level.width && !hits(x)) {
            log(`Moved ${def.id} from x=${def.x} to x=${x} so it doesn't land on the player`, "info");
            def.x = x;
            return;
          }
        }
      }
    }

    defCenter(def) {
      const w = (def.w || 1) * TILE, h = (def.h || 1) * TILE;
      return { cx: def.x * TILE + w / 2, cy: def.y * TILE + h / 2 };
    }

    // ----- change animations -----
    ring(x, y, color = 0xffffff, size = 6) {
      const c = this.add.circle(x, y, size).setStrokeStyle(3, color).setDepth(7);
      this.tweens.add({ targets: c, scale: 5, alpha: 0, duration: 420, ease: "Cubic.easeOut", onComplete: () => c.destroy() });
    }

    popIn(obj) {
      const { cx, cy } = this.defCenter(obj.def);
      this.ring(cx, cy, 0xfff2a0, Math.max(6, ((obj.def.w || 1) * TILE) / 6));
      S.fx.sparkle(cx, cy, 0xfff2a0, 10);
      if (obj.visuals) {
        obj.visuals.forEach((v, i) => {
          const y = v.y;
          v.setAlpha(0).setY(y - 14);
          this.tweens.add({ targets: v, alpha: 1, y, duration: 320, delay: i * 30, ease: "Back.easeOut" });
        });
      } else {
        const sx = obj.scaleX, sy = obj.scaleY;
        obj.setScale(0);
        this.tweens.add({ targets: obj, scaleX: sx, scaleY: sy, duration: 380, ease: "Back.easeOut" });
      }
    }

    pulse(obj) {
      const { cx, cy } = this.defCenter(obj.def);
      const x = obj.visuals ? cx : obj.x, y = obj.visuals ? cy : obj.y;
      this.ring(x, y, 0x9fe8ff);
      S.fx.sparkle(x, y, 0x9fe8ff, 6);
      if (obj.visuals) this.tweens.add({ targets: obj.visuals, alpha: 0.4, duration: 110, yoyo: true, repeat: 1 });
      else this.tweens.add({ targets: obj, scaleX: obj.scaleX * 1.3, scaleY: obj.scaleY * 1.3, duration: 120, yoyo: true, ease: "Quad.easeOut" });
    }

    // Physics or ability change: shockwave around the player plus a quick camera bump.
    globalPulse() {
      const p = this.player;
      this.ring(p.x, p.y, 0xb48cff, 10);
      this.time.delayedCall(120, () => this.ring(p.x, p.y, 0xffffff, 8));
      S.fx.sparkle(p.x, p.y, 0xd9c8ff, 14);
      const cam = this.cameras.main;
      this.tweens.add({ targets: cam, zoom: 1.05, duration: 110, yoyo: true, ease: "Quad.easeOut" });
    }

    showToast(text) {
      const t = this.toast;
      this.tweens.killTweensOf(t);
      t.setText("★ " + text).setAlpha(0).setY(LK.uiY(this, 30));
      this.tweens.add({ targets: t, alpha: 1, y: LK.uiY(this, 44), duration: 220, ease: "Back.easeOut" });
      this.tweens.add({ targets: t, alpha: 0, duration: 400, delay: 2000 });
    }

    hitEnemy(p, en) {
      if (this.dead || !en.active) return;
      if (this.time.now < (en.hurtUntil || 0)) return; // just got hit: no second stomp, no contact damage
      const stomp = p.body.velocity.y > 0 && p.body.bottom <= en.body.top + 14;
      if (stomp) {
        LK.react(this, "stomp", en);
        p.setVelocityY(-this.level.physics.jump_velocity * 0.6);
        if (en.props.stompable !== false) this.damageEnemy(en, 1);
      } else {
        this.hurt("Got hit by an enemy");
      }
    }

    // ----- building blocks for behaviors in mechanics.js (and model-written abilities) -----
    // Hits an enemy can still take: props.hp (default 1) minus hits taken. Changing props.hp live keeps the damage.
    enemyHp(en) { return Math.max(0, (Number(en.props && en.props.hp) || 1) - (en.damage || 0)); }

    // Deal n hits. Brief invulnerability after a hit that doesn't defeat it. Returns false if it couldn't be hit.
    damageEnemy(en, n = 1) {
      if (!en || !en.active || this.time.now < (en.hurtUntil || 0)) return false;
      en.damage = (en.damage || 0) + n;
      if (this.enemyHp(en) <= 0) { this.defeatEnemy(en); return true; }
      en.hurtUntil = this.time.now + 600;
      S.fx.burst(en.x, en.y, 0xffffff, 10);
      this.tweens.add({ targets: en, alpha: 0.3, duration: 75, yoyo: true, repeat: 3, onComplete: () => en.setAlpha(1) });
      return true;
    }

    defeatEnemy(en) {
      if (!en.active) return;
      LK.react(this, "enemy_defeated", en);
      const big = (Number(en.props && en.props.hp) || 1) > 1;
      S.fx.burst(en.x, en.y, en.tintColor ?? 0xe9dcff, big ? 36 : 12);
      if (big) {
        this.cameras.main.shake(350, 0.012);
        this.ring(en.x, en.y, 0xffffff, 16);
        S.fx.sparkle(en.x, en.y, 0xfff2a0, 20);
        this.showToast(`${en.def.id} defeated!`);
        log(`${en.def.id} defeated`, "ok");
      }
      en.disableBody(true, true);
    }

    // A projectile that hurts the player on touch and pops on platforms. look = {sprite, tint, life_ms}.
    spawnEnemyShot(x, y, vx, vy = 0, look = {}) {
      const shot = S.spawnProjectile(this, x, y, vx < 0 ? -1 : 1, { sprite: "fireball_red", ...look, life_ms: look.life_ms || 4000 });
      this.enemyShots.add(shot);
      shot.body.setAllowGravity(false);
      shot.setVelocity(vx, vy);
      return shot;
    }

    // True if world point (px, py) is inside a platform of the current level.
    solidAt(px, py) {
      const tx = Math.floor(px / TILE), ty = Math.floor(py / TILE);
      return this.level.entities.some((e) => e.type === "platform" && tx >= e.x && tx < e.x + (e.w || 1) && ty >= e.y && ty < e.y + (e.h || 1));
    }

    // A goal with props.locked_by = "<id>" can't be reached while that object is still alive.
    isLocked(goal) {
      const lk = goal.def.props && goal.def.props.locked_by;
      const by = lk && this.byId[lk];
      return !!(by && by.active);
    }

    updateLocks() {
      for (const id in this.byId) {
        const g = this.byId[id];
        if (g.def.type !== "goal" || !g.active) continue;
        const locked = this.isLocked(g);
        if (locked === g.wasLocked) continue;
        const first = g.wasLocked === undefined;
        g.wasLocked = locked;
        g.setAlpha(locked ? 0.35 : 1);
        if (!locked && !first) {
          this.ring(g.x, g.y, 0xfff2a0, 12);
          S.fx.sparkle(g.x, g.y, 0xfff2a0, 20);
          this.showToast("The flag is open!");
        }
      }
    }

    drawHpBars() {
      const g = this.hpBars;
      g.clear();
      for (const en of this.enemies.getChildren()) {
        const max = Number(en.props && en.props.hp) || 1;
        if (!en.active || max <= 1) continue;
        const w = Math.max(40, en.body.width), x = en.body.center.x - w / 2, y = en.body.top - 16;
        g.fillStyle(0x000000, 0.6).fillRect(x - 2, y - 2, w + 4, 10);
        g.fillStyle(0xff4d4d).fillRect(x, y, (w * this.enemyHp(en)) / max, 6);
      }
    }

    collect(it) {
      if (this.dead || this.won || !it.active) return;
      const t = it.def.type;
      if (t !== "goal") LK.react(this, t === "coin" ? "coin" : "powerup", it, it.x, it.y);
      if (t === "coin") {
        this.coins++;
        S.fx.sparkle(it.x, it.y, it.tintColor ?? 0xfff2a0);
        it.disableBody(true, true);
      } else if (t === "double_jump") {
        this.hasDoubleJump = true;
        if (it.idleFx) { it.idleFx.destroy(); it.idleFx = null; }
        S.fx.sparkle(it.x, it.y, it.tintColor ?? 0xfff2a0, 14);
        S.fx.flash(this);
        it.disableBody(true, true);
        log("Double jump unlocked", "ok");
      } else if (t === "grow") {
        if (it.idleFx) { it.idleFx.destroy(); it.idleFx = null; }
        S.fx.sparkle(it.x, it.y, it.tintColor ?? 0xffb3b3, 14);
        it.disableBody(true, true);
        this.setPlayerBig(true);
        log("Grew bigger: survives one hit", "ok");
      } else if (t === "goal") {
        if (this.isLocked(it)) {
          if (this.time.now > this.lockHintUntil) {
            this.showToast(`Locked: defeat ${it.def.props.locked_by} first`);
            this.lockHintUntil = this.time.now + 2500;
          }
          return;
        }
        this.win();
      }
      this.updateHud();
    }

    updateHud() {
      const lvl = stage.count > 1 ? `${this.level.name} (${stage.index + 1}/${stage.count})   ` : "";
      this.hud.setText(`${lvl}Coins ${this.coins}/${this.totalCoins}${this.hasDoubleJump ? "   ⬆⬆ double jump" : ""}${this.isBig ? "   ▲ big" : ""}`);
    }

    die(reason) {
      if (this.dead || this.won) return;
      this.dead = true;
      const p = this.player;
      LK.react(this, "die", p);
      S.play(p, "hit");
      S.fx.burst(p.x, Math.min(p.y, this.worldH - 8), p.tintColor ?? 0xff6b5e, 18);
      this.tweens.add({ targets: p, alpha: 0, duration: 350 });
      this.physics.pause();
      this.banner.setText(reason);
      this.time.delayedCall(800, () => this.scene.restart());
    }

    win() {
      if (this.won) return;
      this.won = true;
      LK.react(this, "win", this.player);
      S.fx.confetti(this.player.x, this.player.y - 24, 120);
      this.physics.pause();
      S.fx.sparkle(this.player.x, this.player.y - 10, 0xfff2a0, 20);
      log(`Level complete: ${this.level.name}`, "ok");
      const next = stage.index + 1;
      if (next < stage.count) {
        this.banner.setText(`Level complete!\nCoins ${this.coins}/${this.totalCoins}\nNext: ${stage.names[next] || "level " + (next + 1)}`);
        this.time.delayedCall(2200, () => goToStage(next)); // cancelled if the player restarts with R
      } else {
        this.banner.setText(`You win!\nCoins ${this.coins}/${this.totalCoins}\nPress R to play again`);
      }
    }

    runBehaviors(dt) {
      for (const obj of this.behaving) {
        if (!obj.active) continue;
        for (const name of obj.def.behaviors) {
          if (obj.disabledBehaviors.has(name)) continue;
          const fn = window.MECHANICS[name];
          if (typeof fn !== "function") {
            log(`Behavior '${name}' not found in mechanics.js (entity ${obj.def.id})`, "error");
            obj.disabledBehaviors.add(name);
            continue;
          }
          try {
            fn(obj, this, dt);
          } catch (err) {
            obj.disabledBehaviors.add(name);
            log(`Behavior '${name}' threw on ${obj.def.id}: ${err.message}`, "error");
          }
        }
      }
    }

    update(time, delta) {
      const k = this.keys, c = this.cursors;
      for (const b of this.bg) b.ts.tilePositionX = this.cameras.main.scrollX * b.factor;
      if (Phaser.Input.Keyboard.JustDown(k.R)) { this.scene.restart(); return; }
      if (this.dead || this.won) return;

      this.updateMovingPlatforms(time);

      const p = this.player, phys = this.level.physics;
      const onGround = p.body.blocked.down;
      if (onGround && !this.wasOnGround) LK.react(this, "land", p, p.x, p.body.bottom);
      this.wasOnGround = onGround;
      if (onGround && p.body.velocity.x !== 0) {
        this.stepDist += Math.abs(p.body.velocity.x) * delta / 1000;
        if (this.stepDist > 36) { this.stepDist = 0; LK.react(this, "step", p, p.x, p.body.bottom); }
      }
      if (onGround) { this.lastGroundTime = time; this.jumpedSinceGround = false; this.airJumpsUsed = 0; }

      // run
      const left = c.left.isDown || k.A.isDown, right = c.right.isDown || k.D.isDown;
      p.setVelocityX(left === right ? 0 : left ? -phys.run_speed : phys.run_speed);
      if (left !== right) p.setFlipX(left);

      // jump (coyote time + buffer + optional double jump)
      const jumpDown = Phaser.Input.Keyboard.JustDown(c.space) || Phaser.Input.Keyboard.JustDown(c.up) || Phaser.Input.Keyboard.JustDown(k.W);
      const jumpHeld = c.space.isDown || c.up.isDown || k.W.isDown;
      if (jumpDown) this.jumpBufferUntil = time + JUMP_BUFFER_MS;
      if (time <= this.jumpBufferUntil) {
        if (!this.jumpedSinceGround && time - this.lastGroundTime <= COYOTE_MS) {
          p.setVelocityY(-phys.jump_velocity);
          this.jumpedSinceGround = true;
          this.jumpBufferUntil = 0;
          LK.react(this, "jump", p, p.x, p.body.bottom);
        } else if (jumpDown && this.hasDoubleJump && this.airJumpsUsed < 1 && !onGround) {
          p.setVelocityY(-phys.jump_velocity * 0.9);
          this.airJumpsUsed++;
          this.jumpedSinceGround = true;
          this.jumpBufferUntil = 0;
          S.fx.sparkle(p.x, p.y + PLAYER_H / 2, 0xffffff, 5);
          LK.react(this, "jump", p, p.x, p.body.bottom);
        }
      }
      // variable jump height: release early for a short hop
      if (!jumpHeld && p.body.velocity.y < -150) p.setVelocityY(p.body.velocity.y * 0.85);

      S.play(p, !onGround ? "jump" : left !== right ? "run" : "idle");

      this.runBehaviors(delta / 1000);
      LK.update(this, time);
      this.updateLocks();
      this.drawHpBars();
      this.runAbilities(delta / 1000);

      // fell out of the world
      if (p.y > this.worldH + 40) this.die("Fell into a pit");
      this.enemies.getChildren().forEach((en) => { if (en.active && en.y > this.worldH + 100) en.disableBody(true, true); });
    }

    // Move generic platforms along signed tile offsets and carry a player standing on top.
    updateMovingPlatforms(time) {
      for (const plat of this.motionPlatforms || []) {
        if (!plat.active || !plat.motionOrigin) continue;
        const props = plat.props || {}, period = Math.max(1, Number(props.motion_period) || 4) * 1000;
        const phase = ((time % period) / period) * 2;
        const t = phase <= 1 ? phase : 2 - phase;
        const nx = plat.motionOrigin.x + (Number(props.motion_dx) || 0) * TILE * t;
        const ny = plat.motionOrigin.y + (Number(props.motion_dy) || 0) * TILE * t;
        const dx = nx - plat.x, dy = ny - plat.y;
        if (!dx && !dy) continue;
        const p = this.player, b = p.body, pb = plat.body;
        const riding = b && b.bottom >= pb.top - 4 && b.bottom <= pb.top + 7 && b.right > pb.left && b.left < pb.right;
        this.physics.world.staticTree.remove(plat.body);
        plat.setPosition(nx, ny);
        plat.body.updateFromGameObject();
        this.physics.world.staticTree.insert(plat.body);
        for (const v of plat.visuals || []) v.setPosition(v.x + dx, v.y + dy);
        if (riding) p.setPosition(p.x + dx, p.y + dy);
      }
    }

    refreshMotionPlatforms() {
      this.motionPlatforms = this.platforms.getChildren().filter((o) => o.props && ((Number(o.props.motion_dx) || 0) || (Number(o.props.motion_dy) || 0)));
      for (const o of this.motionPlatforms) if (!o.motionOrigin) o.motionOrigin = { x: o.x, y: o.y };
    }

    drawMicIcon(listening) {
      const g = this.micIcon, x = 904, y = 14, c = listening ? 0x299b5b : 0xc9434e;
      g.clear();
      g.fillStyle(0x171922, 0.92).fillRoundedRect(x, y, 44, 52, 7);
      g.lineStyle(3, c, 1).strokeRoundedRect(x + 1.5, y + 1.5, 41, 49, 6);
      this.micEmoji.setPosition(x + 7, y + 3);
      g.fillStyle(c, 1).fillRoundedRect(x + 15, y + 35, 14, 14, 2);
      this.micV.setPosition(x + 18, y + 35).setColor("#ffffff");
    }

    setListening(on) { this.drawMicIcon(!!on); }

    showCommandResult(label) {
      const x = 14, y = 435, w = Math.min(520, Math.max(180, String(label).length * 7 + 20)), h = 28;
      this.commandBox.clear().fillStyle(0x24262d, 0.92).fillRect(x, y, w, h)
        .lineStyle(2, 0x737780, 1).strokeRect(x, y, w, h);
      this.commandText.setPosition(x + 9, y + 7).setText(String(label)).setAlpha(1);
      this.commandBox.setAlpha(1);
      this.tweens.killTweensOf([this.commandBox, this.commandText]);
      this.tweens.add({ targets: [this.commandBox, this.commandText], alpha: 0, delay: 3800, duration: 450 });
    }
  }

  // ---------- boot ----------
  function activeScene() {
    const scene = game && game.scene.getScene("game");
    return scene && scene.sys.isActive() ? scene : null;
  }

  function loadLevel(level) {
    currentLevel = level;
    const scene = activeScene();
    if (scene) scene.scene.restart();
  }

  // Apply a /api/command patch to the running game without restarting. `level` is the full level after the
  // change (response.level). Falls back to a full reload if live apply throws. Returns true if applied live.
  // `stageIndex` (response.stage) guards against applying a change made to a level that is no longer loaded.
  function applyPatch(ops, level, label, stageIndex) {
    if (stageIndex != null && stageIndex !== stage.index) {
      log(`Ignored a change for level ${stageIndex + 1}; level ${stage.index + 1} is loaded`, "error");
      return false;
    }
    const next = structuredClone(level);
    const scene = activeScene();
    if (!scene || scene.dead) { currentLevel = next; return false; } // a restart is coming anyway
    try {
      scene.applyOps(ops || [], next, label);
      currentLevel = next;
      log(`Applied ${ops.length} change(s) live`, "ok");
      return true;
    } catch (err) {
      log(`Live apply failed (${err.message}); reloading level`, "error");
      loadLevel(next);
      return false;
    }
  }

  function updateStageUi() {
    const bar = document.getElementById("stage-bar");
    if (!bar) return;
    bar.innerHTML = "";
    stage.names.forEach((name, i) => {
      const b = document.createElement("button");
      b.textContent = `${i + 1}. ${name}`;
      if (i === stage.index) b.className = "active";
      b.addEventListener("click", () => goToStage(i));
      bar.appendChild(b);
    });
  }

  // Switch the backend's active level and load it. Edits made to each level are kept when you leave it.
  async function goToStage(i) {
    try {
      const res = await fetch("/api/stage", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ index: i }) });
      const d = await res.json();
      if (!d.ok) { log(`No level ${i + 1}`, "error"); return false; }
      stage = { index: d.index, count: d.count, names: d.names };
      updateStageUi();
      loadLevel(d.level);
      log(`Level ${d.index + 1}/${d.count}: ${d.level.name}`, "ok");
      return true;
    } catch (err) {
      log(`Couldn't switch level: ${err.message}`, "error");
      return false;
    }
  }

  // Phaser schedules the next frame after running the current one, so an exception thrown from a
  // model-written callback would stop the game for good. Wrap the frame callback once it exists.
  function guardLoop() {
    const raf = game && game.loop && game.loop.raf;
    if (!raf || !raf.callback) { setTimeout(guardLoop, 50); return; }
    if (raf.callback.__guarded) return;
    const inner = raf.callback;
    raf.callback = function (t) { try { inner(t); } catch (err) { reportMechanicsError(null, "callback", err); } };
    raf.callback.__guarded = true;
  }

  let game = null;
  async function boot() {
    const [res, st] = await Promise.all([fetch("/api/level"), fetch("/api/stage"), S.init()]);
    currentLevel = await res.json();
    stage = await st.json();
    updateStageUi();
    game = new Phaser.Game({
      type: Phaser.AUTO,
      parent: "game",
      width: 960,
      height: 480,
      physics: { default: "arcade", arcade: { gravity: { y: currentLevel.physics.gravity }, debug: false } },
      scene: [GameScene],
    });
    guardLoop();
    log(`Loaded level "${currentLevel.name}" (${currentLevel.entities.length} entities)`, "ok");
  }

  document.getElementById("reset-btn").addEventListener("click", async () => {
    const res = await fetch("/api/level/reset", { method: "POST" });
    loadLevel(await res.json());
    log("Reset this level to its original layout", "info");
  });

  window.Callout = {
    loadLevel, applyPatch, goToStage, log,
    // Live look changes (no restart). Unknown sprite names fall back to the type's default.
    setAppearance(id, changes) { const s = activeScene(); return s ? s.setAppearance(id, changes) : false; },
    // look: {sprite, tint, bigSprite}; bigSprite is the look while grown by a "grow" power-up.
    setPlayerLook(look) { playerLook = { ...playerLook, ...look }; const s = activeScene(); if (s) s.skinPlayer(); },
    setListening(on) { const s = activeScene(); if (s) s.setListening(on); },
    showCommandResult(label) { const s = activeScene(); if (s) s.showCommandResult(label); },
    // Visual test for projectiles and trails until the fireball runtime (O7) exists.
    debugProjectile(sprite, tint) {
      const s = activeScene();
      if (!s) return null;
      const dir = s.player.flipX ? -1 : 1;
      return S.spawnProjectile(s, s.player.x + dir * 20, s.player.y, dir, { sprite, tint });
    },
    get level() { return currentLevel; },
    get scene() { return game && game.scene.getScene("game"); },
    get stage() { return stage.index; },
  };
  boot();
})();
