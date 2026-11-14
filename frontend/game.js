// game.js — Phaser runtime. Builds a level from JSON and runs it.
// Public API: window.Sketch2Game.loadLevel(levelJson), window.Sketch2Game.log(msg, kind)
(function () {
  const TILE = 32;
  const COYOTE_MS = 100;     // jump grace after leaving a ledge
  const JUMP_BUFFER_MS = 100; // jump pressed slightly before landing still counts
  let currentLevel = null;

  // ---------- side panel log ----------
  function log(msg, kind = "info") {
    const el = document.getElementById("log");
    if (!el) return;
    const div = document.createElement("div");
    div.className = "entry " + kind;
    div.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
    el.prepend(div);
  }
  window.addEventListener("error", (e) => log(`JS error: ${e.message}`, "error"));

  // ---------- textures (drawn in code: no image files, works offline) ----------
  function makeTextures(scene) {
    if (scene.textures.exists("player")) return;
    const g = scene.make.graphics({ add: false });
    const tex = (key, w, h, draw) => { g.clear(); draw(g); g.generateTexture(key, w, h); };

    tex("player", 24, 30, (g) => {
      g.fillStyle(0xe74c3c).fillRect(0, 0, 24, 30);
      g.fillStyle(0x2c3e50).fillRect(0, 0, 24, 8);
      g.fillStyle(0xffffff).fillRect(14, 10, 6, 6);
    });
    tex("enemy", 28, 24, (g) => {
      g.fillStyle(0x8e5a2b).fillRoundedRect(0, 0, 28, 24, 8);
      g.fillStyle(0xffffff).fillRect(4, 6, 6, 6).fillRect(18, 6, 6, 6);
      g.fillStyle(0x000000).fillRect(4, 8, 3, 3).fillRect(18, 8, 3, 3);
    });
    tex("brick", TILE, TILE, (g) => {
      g.fillStyle(0x6b4a2b).fillRect(0, 0, TILE, TILE);
      g.fillStyle(0x4caf50).fillRect(0, 0, TILE, 6);
      g.lineStyle(2, 0x553a20).strokeRect(1, 1, TILE - 2, TILE - 2);
    });
    tex("spike", TILE, TILE, (g) => {
      g.fillStyle(0xbdc3c7);
      g.fillTriangle(0, TILE, 8, 8, 16, TILE).fillTriangle(16, TILE, 24, 8, 32, TILE);
    });
    tex("lava", TILE, TILE, (g) => {
      g.fillStyle(0xe67e22).fillRect(0, 0, TILE, TILE);
      g.fillStyle(0xf1c40f).fillRect(0, 0, TILE, 5);
    });
    tex("coin", 16, 16, (g) => {
      g.fillStyle(0xf1c40f).fillCircle(8, 8, 8);
      g.fillStyle(0xf39c12).fillCircle(8, 8, 4);
    });
    tex("double_jump", 22, 22, (g) => {
      g.fillStyle(0x3498db).fillTriangle(11, 0, 22, 11, 11, 22).fillTriangle(11, 0, 0, 11, 11, 22);
      g.fillStyle(0xffffff).fillTriangle(11, 5, 16, 11, 6, 11);
    });
    tex("goal", TILE, TILE * 2, (g) => {
      g.fillStyle(0xecf0f1).fillRect(14, 0, 4, TILE * 2);
      g.fillStyle(0x9b59b6).fillTriangle(18, 2, 32, 10, 18, 18);
    });
    g.destroy();
  }

  // ---------- scene ----------
  class GameScene extends Phaser.Scene {
    constructor() { super("game"); this.TILE = TILE; }

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
      const W = L.width * TILE, H = L.height * TILE;
      this.worldH = H;
      this.physics.world.gravity.y = L.physics.gravity;
      this.physics.world.setBounds(0, 0, W, H);
      this.physics.world.setBoundsCollision(true, true, true, false); // can fall out the bottom
      this.cameras.main.setBounds(0, 0, W, H).setBackgroundColor("#6ec6ff");

      this.platforms = this.physics.add.staticGroup();
      this.hazards = this.physics.add.staticGroup();
      this.items = this.physics.add.staticGroup();
      this.enemies = this.physics.add.group();
      this.behaving = []; // sprites with behaviors

      for (const e of L.entities) this.spawnEntity(e);

      // player
      const sx = L.spawn.x * TILE + TILE / 2, sy = (L.spawn.y + 1) * TILE - 15;
      this.player = this.physics.add.sprite(sx, sy, "player");
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
    }

    spawnEntity(e) {
      const w = (e.w || 1) * TILE, h = (e.h || 1) * TILE;
      const left = e.x * TILE, top = e.y * TILE, cx = left + w / 2, cy = top + h / 2;
      let obj = null;
      switch (e.type) {
        case "platform":
          obj = this.add.tileSprite(cx, cy, w, h, "brick");
          this.platforms.add(obj);
          break;
        case "spikes":
        case "lava": {
          obj = this.add.tileSprite(cx, cy, w, h, e.type === "spikes" ? "spike" : "lava");
          // forgiving hitbox: lower part of the tiles
          const zone = this.add.zone(cx, top + h * 0.65, w - 6, h * 0.6);
          this.hazards.add(zone);
          break;
        }
        case "enemy":
          obj = this.enemies.create(cx, top + h - 12, "enemy");
          obj.setCollideWorldBounds(true);
          break;
        case "coin":
        case "double_jump":
          obj = this.items.create(cx, cy, e.type);
          break;
        case "goal":
          obj = this.items.create(cx, top + h - TILE, "goal");
          break;
        default:
          log(`Unknown entity type '${e.type}' (${e.id})`, "error");
          return;
      }
      obj.def = e;
      obj.props = e.props || {};
      obj.state = {};
      obj.disabledBehaviors = new Set();
      if (e.behaviors && e.behaviors.length) this.behaving.push(obj);
    }

    hitEnemy(p, en) {
      if (this.dead || !en.active) return;
      const stomp = p.body.velocity.y > 0 && p.body.bottom <= en.body.top + 14;
      if (stomp) {
        en.disableBody(true, true);
        p.setVelocityY(-this.level.physics.jump_velocity * 0.6);
      } else {
        this.die("Got hit by an enemy");
      }
    }

    collect(it) {
      if (this.dead || this.won || !it.active) return;
      const t = it.def.type;
      if (t === "coin") { this.coins++; it.disableBody(true, true); }
      else if (t === "double_jump") { this.hasDoubleJump = true; it.disableBody(true, true); log("Double jump unlocked", "ok"); }
      else if (t === "goal") { this.win(); }
      this.updateHud();
    }

    updateHud() {
      this.hud.setText(`Coins ${this.coins}/${this.totalCoins}${this.hasDoubleJump ? "   ⬆⬆ double jump" : ""}`);
    }

    die(reason) {
      if (this.dead || this.won) return;
      this.dead = true;
      this.player.setTint(0x000000);
      this.physics.pause();
      this.banner.setText(reason);
      this.time.delayedCall(800, () => this.scene.restart());
    }

    win() {
      if (this.won) return;
      this.won = true;
      this.physics.pause();
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
            // Feature 3: report to backend + roll back mechanics.js here.
          }
        }
      }
    }

    update(time, delta) {
      const k = this.keys, c = this.cursors;
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
        }
      }
      // variable jump height: release early for a short hop
      if (!jumpHeld && p.body.velocity.y < -150) p.setVelocityY(p.body.velocity.y * 0.85);

      this.runBehaviors(delta / 1000);

      // fell out of the world
      if (p.y > this.worldH + 40) this.die("Fell into a pit");
      this.enemies.getChildren().forEach((en) => { if (en.active && en.y > this.worldH + 100) en.disableBody(true, true); });
    }
  }

  // ---------- boot ----------
  function loadLevel(level) {
    currentLevel = level;
    const scene = game && game.scene.getScene("game");
    if (scene && scene.sys.isActive()) scene.scene.restart();
  }

  let game = null;
  async function boot() {
    const res = await fetch("/api/level");
    currentLevel = await res.json();
    game = new Phaser.Game({
      type: Phaser.AUTO,
      parent: "game",
      width: 960,
      height: 480,
      physics: { default: "arcade", arcade: { gravity: { y: currentLevel.physics.gravity }, debug: false } },
      scene: [GameScene],
    });
    log(`Loaded level "${currentLevel.name}" (${currentLevel.entities.length} entities)`, "ok");
  }

  document.getElementById("reset-btn").addEventListener("click", async () => {
    const res = await fetch("/api/level/reset", { method: "POST" });
    loadLevel(await res.json());
    log("Reset to sample level", "info");
  });

  window.Sketch2Game = { loadLevel, log, get level() { return currentLevel; }, get scene() { return game && game.scene.getScene("game"); } };
  boot();
})();
