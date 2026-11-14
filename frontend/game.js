// game.js — Phaser runtime. Builds a level from JSON and runs it.
// Public API (window.Sketch2Game): loadLevel(levelJson), log(msg, kind), setAppearance(id, {sprite, tint}),
//   setPlayerLook({sprite, tint}), debugProjectile(sprite, tint), .level, .scene
// Sprites and effects come from sprites.js (window.SPRITES); see assets/catalog.json.
(function () {
  const TILE = 32;
  const COYOTE_MS = 100;     // jump grace after leaving a ledge
  const JUMP_BUFFER_MS = 100; // jump pressed slightly before landing still counts
  const PLAYER_W = 24, PLAYER_H = 30, ENEMY_W = 28, ENEMY_H = 24; // physics bodies (world px); art is skinned around them
  const S = window.SPRITES;
  let currentLevel = null;
  let playerLook = {}; // { sprite?, tint? }; survives restarts

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
    tex("enemy", ENEMY_W, ENEMY_H, (g) => g.fillStyle(0x8e5a2b).fillRect(0, 0, ENEMY_W, ENEMY_H));
    tex("platform", TILE, TILE, (g) => { g.fillStyle(0x6b4a2b).fillRect(0, 0, TILE, TILE); g.lineStyle(2, 0x553a20).strokeRect(1, 1, TILE - 2, TILE - 2); });
    tex("spikes", TILE, TILE, (g) => g.fillStyle(0xbdc3c7).fillRect(0, TILE / 2, TILE, TILE / 2));
    tex("lava", TILE, TILE, (g) => g.fillStyle(0xe67e22).fillRect(0, 0, TILE, TILE));
    tex("coin", 16, 16, (g) => g.fillStyle(0xf1c40f).fillRect(0, 0, 16, 16));
    tex("double_jump", 22, 22, (g) => g.fillStyle(0x3498db).fillRect(0, 0, 22, 22));
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
      this.airJumpsUsed = 0;
      this.lastGroundTime = -9999;
      this.jumpedSinceGround = false;
      this.jumpBufferUntil = 0;

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

      this.platforms = this.physics.add.staticGroup();
      this.hazards = this.physics.add.staticGroup();
      this.items = this.physics.add.staticGroup();
      this.enemies = this.physics.add.group();
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
      this.physics.add.overlap(this.player, this.hazards, () => this.die("Ouch! Hazard"));
      this.physics.add.overlap(this.player, this.enemies, (p, en) => this.hitEnemy(p, en));
      this.physics.add.overlap(this.player, this.items, (p, it) => this.collect(it));

      this.cameras.main.startFollow(this.player, true, 0.15, 0.15);

      // input
      this.cursors = this.input.keyboard.createCursorKeys();
      this.keys = this.input.keyboard.addKeys("W,A,S,D,R");

      // HUD
      this.hud = this.add.text(10, 8, "", { fontFamily: "monospace", fontSize: "16px", color: "#fff", stroke: "#000", strokeThickness: 3 })
        .setScrollFactor(0).setDepth(10);
      this.banner = this.add.text(480, 200, "", { fontFamily: "monospace", fontSize: "32px", color: "#fff", stroke: "#000", strokeThickness: 5, align: "center" })
        .setOrigin(0.5).setScrollFactor(0).setDepth(10);
      this.updateHud();
      this.installAbilities();
    }

    installAbilities() {
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
        this.bg.push({ ts, factor });
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
          this.platforms.add(obj);
          break;
        case "spikes":
        case "lava":
          // forgiving hitbox: lower part of the tiles
          obj = this.add.zone(cx, top + h * 0.65, w - 6, h * 0.6);
          this.hazards.add(obj);
          break;
        case "enemy":
          obj = this.enemies.create(cx, top + h - ENEMY_H / 2, "enemy").setDepth(2);
          obj.setCollideWorldBounds(true);
          break;
        case "coin":
        case "double_jump":
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
      if (t === "platform" || t === "spikes" || t === "lava") {
        (obj.visuals || []).forEach((v) => v.destroy());
        obj.visuals = S.buildArea(this, entry, t, left, top, e.w || 1, e.h || 1);
      } else if (t === "enemy") {
        S.skinDynamic(this, obj, entry, "enemy", ENEMY_W, ENEMY_H);
        S.play(obj, "walk");
      } else if (t === "coin") {
        S.skinStatic(this, obj, entry, "coin", cx, cy, cx, cy, 16, 16);
        S.play(obj, "spin");
      } else if (t === "double_jump") {
        S.skinStatic(this, obj, entry, "double_jump", cx, cy, cx, cy, 22, 22);
        if (!obj.idleFx && obj.active) obj.idleFx = S.fx.idle(cx, cy);
      } else if (t === "goal") {
        // flag art is 2 tiles tall with the pole on its left edge; hitbox stays the full entity rect
        const artX = entry ? left + (entry.size[0] * (entry.scale || 1)) / 2 + 6 : cx;
        const artY = entry ? top + h - (entry.size[1] * (entry.scale || 1)) / 2 : cy;
        S.skinStatic(this, obj, entry, "goal", artX, artY, cx, cy, w, h);
        S.play(obj, "wave");
      }
      S.applyTint(obj, entry, e.tint);
    }

    skinPlayer() {
      const entry = S.resolve(this, "player", playerLook.sprite);
      S.skinDynamic(this, this.player, entry, "player", PLAYER_W, PLAYER_H);
      S.applyTint(this.player, entry, playerLook.tint);
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

    hitEnemy(p, en) {
      if (this.dead || !en.active) return;
      const stomp = p.body.velocity.y > 0 && p.body.bottom <= en.body.top + 14;
      if (stomp) {
        S.fx.burst(en.x, en.y, en.tintColor ?? 0xe9dcff, 12);
        en.disableBody(true, true);
        p.setVelocityY(-this.level.physics.jump_velocity * 0.6);
      } else {
        this.die("Got hit by an enemy");
      }
    }

    collect(it) {
      if (this.dead || this.won || !it.active) return;
      const t = it.def.type;
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
      } else if (t === "goal") { this.win(); }
      this.updateHud();
    }

    updateHud() {
      this.hud.setText(`Coins ${this.coins}/${this.totalCoins}${this.hasDoubleJump ? "   ⬆⬆ double jump" : ""}`);
    }

    die(reason) {
      if (this.dead || this.won) return;
      this.dead = true;
      const p = this.player;
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
      this.physics.pause();
      S.fx.sparkle(this.player.x, this.player.y - 10, 0xfff2a0, 20);
      this.banner.setText(`You win!\nCoins ${this.coins}/${this.totalCoins}\nPress R to play again`);
      log("Level complete", "ok");
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

      const p = this.player, phys = this.level.physics;
      const onGround = p.body.blocked.down;
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
        } else if (jumpDown && this.hasDoubleJump && this.airJumpsUsed < 1 && !onGround) {
          p.setVelocityY(-phys.jump_velocity * 0.9);
          this.airJumpsUsed++;
          this.jumpedSinceGround = true;
          this.jumpBufferUntil = 0;
          S.fx.sparkle(p.x, p.y + PLAYER_H / 2, 0xffffff, 5);
        }
      }
      // variable jump height: release early for a short hop
      if (!jumpHeld && p.body.velocity.y < -150) p.setVelocityY(p.body.velocity.y * 0.85);

      S.play(p, !onGround ? "jump" : left !== right ? "run" : "idle");

      this.runBehaviors(delta / 1000);
      this.runAbilities(delta / 1000);

      // fell out of the world
      if (p.y > this.worldH + 40) this.die("Fell into a pit");
      this.enemies.getChildren().forEach((en) => { if (en.active && en.y > this.worldH + 100) en.disableBody(true, true); });
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
    const [res] = await Promise.all([fetch("/api/level"), S.init()]);
    currentLevel = await res.json();
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
    log("Reset to sample level", "info");
  });

  window.Sketch2Game = {
    loadLevel, log,
    // Live look changes (no restart). Unknown sprite names fall back to the type's default.
    setAppearance(id, changes) { const s = activeScene(); return s ? s.setAppearance(id, changes) : false; },
    setPlayerLook(look) { playerLook = { ...playerLook, ...look }; const s = activeScene(); if (s) s.skinPlayer(); },
    // Visual test for projectiles and trails until the fireball runtime (O7) exists.
    debugProjectile(sprite, tint) {
      const s = activeScene();
      if (!s) return null;
      const dir = s.player.flipX ? -1 : 1;
      return S.spawnProjectile(s, s.player.x + dir * 20, s.player.y, dir, { sprite, tint });
    },
    get level() { return currentLevel; },
    get scene() { return game && game.scene.getScene("game"); },
  };
  boot();
})();
