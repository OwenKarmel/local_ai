// sprites.js — sprite catalog, skins with fallbacks, and particle effects.
// Loads assets/catalog.json (built by tools/build_catalog.py). Everything is local: no network assets.
// A bad or missing sprite never throws: unknown name -> default for the type -> generated colored rectangle.
(function () {
  const TILE = 32;
  const S = { catalog: {}, defaults: {}, warned: new Set() };
  const key = (file) => "s:" + file;
  S.key = key;

  function warn(msg) {
    if (S.warned.has(msg)) return;
    S.warned.add(msg);
    if (window.Sketch2Game && window.Sketch2Game.log) window.Sketch2Game.log(msg, "error");
    else console.warn(msg);
  }

  // ---------- loading ----------
  S.init = async function () {
    try {
      const c = await (await fetch("assets/catalog.json")).json();
      for (const e of c.sprites) S.catalog[e.name] = e;
      S.defaults = c.defaults || {};
    } catch (err) {
      warn("Sprite catalog failed to load; using plain shapes. " + err.message);
    }
  };

  S.preload = function (scene) {
    const files = new Set();
    for (const e of Object.values(S.catalog)) {
      files.add(e.file);
      for (const a of Object.values(e.animations || {})) a.frames.forEach((f) => files.add(f));
      for (const f of Object.values(e.tiles || {})) files.add(f);
    }
    files.forEach((f) => { if (!scene.textures.exists(key(f))) scene.load.image(key(f), "assets/sprites/" + f); });
    scene.load.on("loaderror", (file) => warn(`Sprite file failed to load: ${file.src || file.key}`));
  };

  S.createAnims = function (scene) {
    for (const e of Object.values(S.catalog)) {
      for (const [an, a] of Object.entries(e.animations || {})) {
        const k = e.name + ":" + an;
        if (scene.anims.exists(k) || !a.frames.every((f) => scene.textures.exists(key(f)))) continue;
        scene.anims.create({ key: k, frames: a.frames.map((f) => ({ key: key(f) })), frameRate: a.fps || 6, repeat: -1 });
      }
    }
  };

  // ---------- lookup ----------
  // Catalog entry to draw `type` with, honoring an optional sprite name. null = use the generated fallback texture.
  S.resolve = function (scene, type, name) {
    let e = null;
    if (name != null) {
      e = S.catalog[name];
      if (!e) warn(`Unknown sprite "${name}"; using the default ${type} sprite.`);
      else if (!scene.textures.exists(key(e.file))) e = null;
    }
    if (!e) {
      e = S.catalog[S.defaults[type]];
      if (e && !scene.textures.exists(key(e.file))) e = null;
    }
    return e || null;
  };

  // "#3399ff" / "3399ff" / 0x3399ff -> number, else null.
  S.tint = function (v) {
    if (v == null || v === "") return null;
    if (typeof v === "number" && isFinite(v)) return v & 0xffffff;
    if (typeof v === "string" && /^#?[0-9a-f]{6}$/i.test(v.trim())) return parseInt(v.trim().replace("#", ""), 16);
    warn(`Bad tint "${v}"; expected a hex color like #3399ff.`);
    return null;
  };

  S.applyTint = function (obj, entry, tint) {
    const t = S.tint(tint) ?? S.tint(entry && entry.tint);
    for (const o of obj.visuals || [obj]) { if (t == null) o.clearTint(); else o.setTint(t); }
    obj.tintColor = t;
  };

  S.play = function (obj, anim) {
    const e = obj.look;
    if (!e || !obj.anims) return;
    const k = e.name + ":" + anim;
    if (obj.scene.anims.exists(k)) obj.anims.play(k, true);
  };

  // ---------- skins ----------
  // Dynamic sprite (player, enemy, projectile). Keeps the physics body at exactly bw x bh world px,
  // feet at the bottom of the art, and makes sprite.x/y the body center.
  S.skinDynamic = function (scene, obj, entry, fallbackKey, bw, bh) {
    obj.look = entry;
    if (obj.anims) obj.anims.stop();
    if (!entry) {
      obj.setTexture(fallbackKey).setScale(1).setOrigin(0.5, 0.5);
      if (obj.body) { obj.body.setSize(bw, bh); obj.body.setOffset((obj.width - bw) / 2, (obj.height - bh) / 2); }
      return;
    }
    const s = entry.scale || 0.5, [fw, fh] = entry.size;
    obj.setTexture(key(entry.file)).setScale(s);
    const w = bw / s, h = bh / s, ox = (fw - w) / 2, oy = fh - h;
    obj.setOrigin(0.5, (oy + h / 2) / fh);
    if (obj.body) { obj.body.setSize(w, h); obj.body.setOffset(ox, oy); }
  };

  // Static item (coin, power-up, goal): art at (x, y), hitbox bw x bh centered at (bx, by).
  S.skinStatic = function (scene, obj, entry, fallbackKey, x, y, bx, by, bw, bh) {
    obj.look = entry;
    if (obj.anims) obj.anims.stop();
    if (entry) obj.setTexture(key(entry.file)).setScale(entry.scale || 0.5);
    else obj.setTexture(fallbackKey).setScale(1);
    obj.setOrigin(0.5, 0.5).setPosition(x, y);
    const b = obj.body;
    if (b) {
      scene.physics.world.staticTree.remove(b);
      b.position.set(bx - bw / 2, by - bh / 2);
      b.setSize(bw, bh, false); // re-inserts into the static tree
    }
  };

  // Tiled visuals for an area entity (platform, spikes, lava). Returns an array of game objects.
  S.buildArea = function (scene, entry, fallbackKey, left, top, wt, ht) {
    const out = [];
    const ok = (f) => f && scene.textures.exists(key(f));
    const strip = (file, tx, ty, tw, th) => {
      if (tw <= 0 || th <= 0) return;
      const src = scene.textures.get(key(file)).getSourceImage();
      const ts = scene.add.tileSprite(left + tx * TILE, top + ty * TILE, tw * TILE, th * TILE, key(file)).setOrigin(0, 0);
      ts.setTileScale(TILE / src.width, TILE / src.height);
      out.push(ts);
    };
    if (!entry) {
      out.push(scene.add.tileSprite(left, top, wt * TILE, ht * TILE, fallbackKey).setOrigin(0, 0));
      return out;
    }
    const t = entry.tiles || {};
    const full = ["top_left", "top", "top_right", "left", "center", "right", "h_left", "h_middle", "h_right", "single"].every((k) => ok(t[k]));
    if (full) { // platform tileset: caps + tiled middle
      if (ht === 1) {
        if (wt === 1) strip(t.single, 0, 0, 1, 1);
        else { strip(t.h_left, 0, 0, 1, 1); strip(t.h_middle, 1, 0, wt - 2, 1); strip(t.h_right, wt - 1, 0, 1, 1); }
      } else if (wt === 1) {
        strip(t.top, 0, 0, 1, 1); strip(t.center, 0, 1, 1, ht - 1);
      } else {
        strip(t.top_left, 0, 0, 1, 1); strip(t.top, 1, 0, wt - 2, 1); strip(t.top_right, wt - 1, 0, 1, 1);
        strip(t.left, 0, 1, 1, ht - 1); strip(t.center, 1, 1, wt - 2, ht - 1); strip(t.right, wt - 1, 1, 1, ht - 1);
      }
    } else if (ok(t.top) && ok(t.center)) { // liquid: surface row + body
      strip(t.top, 0, 0, wt, 1); strip(t.center, 0, 1, wt, ht - 1);
    } else {
      strip(entry.file, 0, 0, wt, ht);
    }
    return out;
  };

  // ---------- effects ----------
  S.fx = {
    init(scene) {
      this.scene = scene;
      const dot = scene.textures.exists(key("effect_spark.png")) ? key("effect_spark.png") : "fx_dot";
      const star = scene.textures.exists(key("effect_star.png")) ? key("effect_star.png") : "fx_dot";
      this.dot = dot; this.star = star;
      this.burstEm = scene.add.particles(0, 0, dot, {
        speed: { min: 60, max: 210 }, angle: { min: 0, max: 360 }, lifespan: { min: 250, max: 520 },
        scale: { start: 1.3, end: 0 }, gravityY: 420, emitting: false,
      }).setDepth(6);
      this.sparkEm = scene.add.particles(0, 0, star, {
        speed: { min: 30, max: 110 }, angle: { min: 0, max: 360 }, lifespan: { min: 300, max: 520 },
        scale: { start: 0.6, end: 0 }, rotate: { min: 0, max: 360 }, emitting: false,
      }).setDepth(6);
    },
    burst(x, y, color = 0xffffff, n = 10) { this.burstEm.setParticleTint(color); this.burstEm.explode(n, x, y); },
    sparkle(x, y, color = 0xfff2a0, n = 7) { this.sparkEm.setParticleTint(color); this.sparkEm.explode(n, x, y); },
    // Gentle looping sparkle around a resting item. Caller destroys the returned emitter.
    idle(x, y, color = 0xfff2a0) {
      return this.scene.add.particles(x, y, this.star, {
        x: { min: -15, max: 15 }, y: { min: -15, max: 15 }, speedY: { min: -25, max: -8 }, lifespan: 700,
        scale: { start: 0.45, end: 0 }, alpha: { start: 1, end: 0 }, frequency: 320, quantity: 1, tint: color,
      }).setDepth(6);
    },
    // Glowing trail that follows a moving sprite; its color tracks sprite.trailColor (set by S.setProjectileLook).
    trail(sprite) {
      const scene = this.scene;
      const em = scene.add.particles(0, 0, this.dot, {
        follow: sprite, lifespan: 300, speed: { min: 0, max: 25 }, scale: { start: 1.6, end: 0 }, alpha: { start: 0.9, end: 0 },
        frequency: 16, quantity: 1, tint: { onEmit: () => sprite.trailColor ?? 0xffa030 },
      }).setDepth(5);
      sprite.once("destroy", () => { em.stop(); scene.time.delayedCall(400, () => em.destroy()); });
      return em;
    },
    flash(scene) { scene.cameras.main.flash(160, 255, 255, 220); },
  };

  // ---------- projectiles (visuals only; shooting rules belong to the fireball task, O7) ----------
  // look = { sprite?: catalog name, tint?: hex }. Safe to call again on a live projectile to re-skin it.
  S.setProjectileLook = function (scene, p, look = {}) {
    const entry = S.resolve(scene, "projectile", look.sprite);
    S.skinDynamic(scene, p, entry, "fx_ball", 14, 14);
    S.applyTint(p, entry, look.tint);
    p.trailColor = p.tintColor ?? S.tint(entry && entry.trail) ?? 0xffa030;
  };

  S.spawnProjectile = function (scene, x, y, dir, opts = {}) {
    const p = scene.physics.add.sprite(x, y, "fx_ball");
    p.body.allowGravity = false;
    S.setProjectileLook(scene, p, opts);
    p.setVelocityX(dir * (opts.speed || 420)).setFlipX(dir < 0).setDepth(4);
    S.fx.trail(p);
    scene.time.delayedCall(opts.life_ms || 1500, () => p.active && p.destroy());
    return p;
  };

  window.SPRITES = S;
})();
