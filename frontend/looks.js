// looks.js — visual-only building blocks: per-object looks, the whole-screen scene look, and event reactions.
// Data comes from the level JSON (entity.look, level.player_look, level.scene, level.reactions; backend/schema.py).
// Nothing here changes gameplay. Every entry point catches its own errors: a bad look never breaks the game.
// Public API (window.LOOKS): applyObject(scene, obj, look, kind), applyScene(scene, sceneLook), react(scene, event, actor, x, y),
//   update(scene, time), init(scene)
(function () {
  const S = window.SPRITES;
  const VIEW_W = 960, VIEW_H = 480;
  const L = {};

  function safe(name, fn) {
    try { return fn(); } catch (err) {
      const msg = `Look '${name}' failed: ${err.message}`;
      if (window.Callout) window.Callout.log(msg, "error"); else console.warn(msg);
    }
  }
  const hex = (v, d = null) => (v == null ? d : S.tint(v) ?? d);

  // ---------- textures for particles (drawn in code; no image files) ----------
  function textures(scene) {
    if (scene.textures.exists("lk_drop")) return;
    const g = scene.make.graphics({ add: false });
    const tex = (k, w, h, draw) => { g.clear(); draw(g); g.generateTexture(k, w, h); };
    tex("lk_drop", 2, 14, (g) => g.fillStyle(0xffffff).fillRect(0, 0, 2, 14));
    tex("lk_dot", 8, 8, (g) => g.fillStyle(0xffffff).fillCircle(4, 4, 4));
    tex("lk_leaf", 12, 7, (g) => g.fillStyle(0xffffff).fillEllipse(6, 3.5, 12, 7));
    tex("lk_square", 7, 7, (g) => g.fillStyle(0xffffff).fillRect(0, 0, 7, 7));
    tex("lk_ring", 16, 16, (g) => g.lineStyle(2, 0xffffff).strokeCircle(8, 8, 6));
    tex("lk_print", 10, 5, (g) => g.fillStyle(0xffffff).fillEllipse(5, 2.5, 10, 5));
    tex("lk_soft", 128, 128, (g) => { for (let r = 64; r > 0; r -= 8) g.fillStyle(0xffffff, 0.09).fillCircle(64, 64, r); });
    g.destroy();
  }

  L.init = function (scene) {
    textures(scene);
    scene.lookItems = new Set(); // objects with per-frame effects (rainbow, flicker, blink, fade_far)
    scene.sceneFx = {};          // current scene-look objects (sky, overlay, weather emitters, camera FX)
  };

  // ---------- per-object looks ----------
  // kind: "area" (platform/spikes/lava: obj.visuals), "static" (coin, powerup, goal), "dynamic" (player, enemy).
  // Size for dynamic objects is applied by the skin (S.skinDynamic mul) so the body stays right; here: everything else.
  // Moving objects (player, enemies) keep their position: their lookBase is only where they stood when the look
  // was first applied (for the player, the spawn point), so restoring it would teleport them.
  function clearObject(scene, obj, kind) {
    for (const t of obj._lookTweens || []) t.remove();
    for (const em of obj._lookEmitters || []) em.destroy();
    for (const o of obj.visuals || [obj]) {
      if (o._glow && o.preFX) { o.preFX.remove(o._glow); o._glow = null; }
      if (o.lookBase) { o.setAngle(0); if (kind !== "dynamic") o.setPosition(o.lookBase.x, o.lookBase.y); }
    }
    obj._lookTweens = []; obj._lookEmitters = [];
    scene.lookItems.delete(obj);
  }

  L.applyObject = function (scene, obj, look, kind) {
    safe("object", () => {
      if (!scene.lookItems) L.init(scene);
      clearObject(scene, obj, kind);
      look = look || {};
      const targets = obj.visuals || [obj];
      const sx = (look.scale || 1) * (look.scale_x || 1), sy = (look.scale || 1) * (look.scale_y || 1);
      const alpha = look.alpha ?? 1;
      obj.lookAlpha = alpha;
      for (const o of targets) {
        o.lookBase = { x: o.x, y: o.y };
        o.setAlpha(alpha);
        if (o.setFlipY) o.setFlipY(!!look.flip_y);
      }
      if (kind === "static" && (sx !== 1 || sy !== 1)) obj.setScale(obj.scaleX * sx, obj.scaleY * sy);
      if (kind === "area" && obj.def && obj.def.type !== "platform" && (sx !== 1 || sy !== 1)) {
        // hazards: stretch the art from the bottom-center of the area (the hitbox stays the same)
        const T = 32, d = obj.def, cx = (d.x + (d.w || 1) / 2) * T, by = (d.y + (d.h || 1)) * T;
        for (const o of targets) {
          o.setScale(sx, sy).setPosition(cx + (o.lookBase.x - cx) * sx, by - (by - o.lookBase.y) * sy);
          o.lookBase = { x: o.x, y: o.y };
        }
      }
      const glow = hex(look.glow);
      if (glow != null) for (const o of targets) if (o.preFX) o._glow = o.preFX.addGlow(glow, 4, 0, false, 0.1, 12);

      const fx = new Set(look.effects || []);
      const tw = (cfg) => obj._lookTweens.push(scene.tweens.add(cfg));
      const fit = kind === "dynamic" ? () => S.fitBody(obj) : undefined;
      if (fx.has("pulse")) {
        if (kind === "area") tw({ targets, alpha: alpha * 0.55, duration: 600, yoyo: true, repeat: -1, ease: "Sine.easeInOut" });
        else tw({ targets: obj, scaleX: obj.scaleX * 1.15, scaleY: obj.scaleY * 1.15, duration: 520, yoyo: true, repeat: -1,
                  ease: "Sine.easeInOut", onUpdate: fit });
      }
      if (kind !== "area") {
        if (fx.has("spin")) tw({ targets: obj, angle: 360, duration: 1400, repeat: -1 });
        else if (fx.has("wobble")) { obj.setAngle(-10); tw({ targets: obj, angle: 10, duration: 380, yoyo: true, repeat: -1, ease: "Sine.easeInOut" }); }
      }
      if (fx.has("bob") && kind !== "dynamic") tw({ targets, y: "-=6", duration: 700, yoyo: true, repeat: -1, ease: "Sine.easeInOut" });
      if (fx.has("sparkle")) {
        const w = obj.visuals ? (obj.def.w || 1) * 32 : 30, h = obj.visuals ? (obj.def.h || 1) * 32 : 30;
        const c = obj.visuals ? { x: obj.def.x * 32 + w / 2, y: obj.def.y * 32 + h / 2 } : obj;
        const em = scene.add.particles(0, 0, S.fx.star || "lk_dot", {
          x: { min: -w / 2, max: w / 2 }, y: { min: -h / 2, max: h / 2 }, speedY: { min: -30, max: -8 }, lifespan: 650,
          scale: { start: 0.45, end: 0 }, alpha: { start: 1, end: 0 }, frequency: obj.visuals ? 90 : 150,
          tint: obj.tintColor ?? 0xfff2a0, ...(obj.visuals ? {} : { follow: obj }),
        }).setDepth(6);
        if (obj.visuals) em.setPosition(c.x, c.y);
        obj._lookEmitters.push(em);
      }
      if (fx.has("trail") && kind !== "area") {
        obj._lookEmitters.push(scene.add.particles(0, 0, "lk_dot", {
          follow: obj, lifespan: 420, speed: { min: 0, max: 15 }, scale: { start: 1.4, end: 0 }, alpha: { start: 0.8, end: 0 },
          frequency: 22, tint: { onEmit: () => obj.recolorColor ?? obj.tintColor ?? 0x9fe8ff },
        }).setDepth((obj.depth || 2) - 0.5));
      }
      const perFrame = ["rainbow", "flicker", "blink", "fade_far"].filter((e) => fx.has(e));
      if (perFrame.length) { obj.lookFrame = perFrame; scene.lookItems.add(obj); }
    });
  };

  L.update = function (scene, time) {
    if (!scene.lookItems || !scene.lookItems.size) return;
    safe("update", () => {
      const p = scene.player;
      let i = 0;
      for (const obj of scene.lookItems) {
        i++;
        if (!obj.scene || (!obj.visuals && !obj.active)) { // collected / destroyed
          for (const em of obj._lookEmitters || []) em.destroy();
          obj._lookEmitters = [];
          scene.lookItems.delete(obj);
          continue;
        }
        const targets = obj.visuals || [obj], fx = obj.lookFrame;
        let a = obj.lookAlpha ?? 1;
        if (fx.includes("rainbow")) {
          const c = Phaser.Display.Color.HSVToRGB(((time / 1000) * 0.35 + i * 0.13) % 1, 0.75, 1).color;
          for (const o of targets) S.recolor(o, c);
        }
        if (fx.includes("flicker")) {
          if (!obj._flickT || time > obj._flickT) { obj._flickV = 0.25 + Math.random() * 0.75; obj._flickT = time + 50 + Math.random() * 90; }
          a *= obj._flickV;
        }
        if (fx.includes("blink") && Math.floor(time / 300) % 2) a *= 0.2;
        if (fx.includes("fade_far") && p) {
          const cx = obj.visuals ? (obj.def.x + (obj.def.w || 1) / 2) * 32 : obj.x, cy = obj.visuals ? obj.def.y * 32 : obj.y;
          const d = Math.hypot(cx - p.x, cy - p.y);
          a *= Phaser.Math.Clamp(1.15 - d / 220, 0.08, 1);
        }
        for (const o of targets) o.setAlpha(a);
      }
    });
  };

  // ---------- whole-screen look ----------
  const WEATHER = {
    rain: (c) => ({ tex: "lk_drop", cfg: { x: { min: -100, max: VIEW_W + 100 }, y: -20, speedY: { min: 520, max: 720 }, speedX: -70,
      lifespan: 1100, frequency: 12, quantity: 2, alpha: 0.55, tint: c ?? 0xa8d0ff, rotate: 6, advance: 1500 } }),
    snow: (c) => ({ tex: "lk_dot", cfg: { x: { min: -50, max: VIEW_W + 50 }, y: -10, speedY: { min: 35, max: 85 }, speedX: { min: -25, max: 25 },
      scale: { min: 0.35, max: 1 }, lifespan: 9000, frequency: 55, alpha: 0.9, tint: c ?? 0xffffff, advance: 8000 } }),
    leaves: (c) => ({ tex: "lk_leaf", cfg: { x: { min: 0, max: VIEW_W + 100 }, y: -10, speedY: { min: 40, max: 80 }, speedX: { min: -50, max: 15 },
      rotate: { start: 0, end: 540 }, lifespan: 9000, frequency: 260, tint: c ?? [0xe8761a, 0xc4401c, 0xe8b31a, 0x9a6b2a], advance: 8000 } }),
    stars: (c) => ({ tex: "lk_dot", cfg: { x: { min: 0, max: VIEW_W }, y: { min: 0, max: VIEW_H * 0.6 }, speed: 0, scale: { min: 0.2, max: 0.6 },
      alpha: { start: 1, end: 0, ease: "Sine.easeIn" }, lifespan: { min: 1500, max: 4000 }, frequency: 35, tint: c ?? 0xfff8d0, advance: 4000 } }),
    bubbles: (c) => ({ tex: "lk_ring", cfg: { x: { min: 0, max: VIEW_W }, y: VIEW_H + 10, speedY: { min: -100, max: -40 }, speedX: { min: -12, max: 12 },
      scale: { min: 0.4, max: 1.1 }, alpha: 0.7, lifespan: 7000, frequency: 160, tint: c ?? 0xc8f0ff, advance: 6000 } }),
    embers: (c) => ({ tex: "lk_dot", cfg: { x: { min: 0, max: VIEW_W }, y: VIEW_H + 10, speedY: { min: -90, max: -30 }, speedX: { min: -20, max: 20 },
      scale: { start: 0.7, end: 0 }, lifespan: 5500, frequency: 80, tint: c ?? [0xff7a1a, 0xff3d1a, 0xffc21a], blendMode: "ADD", advance: 5000 } }),
    fog: (c) => ({ tex: "lk_soft", cfg: { x: { min: -200, max: VIEW_W }, y: { min: VIEW_H * 0.35, max: VIEW_H }, speedX: { min: 6, max: 22 },
      scale: { min: 2, max: 4 }, alpha: { start: 0, end: 0.3, ease: "Sine.easeOut" }, lifespan: 10000, frequency: 260, tint: c ?? 0xe8eef2, advance: 9000 } }),
    clouds: (c) => ({ tex: "lk_soft", cfg: { x: -250, y: { min: 10, max: 170 }, speedX: { min: 10, max: 28 }, scaleX: { min: 3, max: 5 },
      scaleY: { min: 1, max: 1.6 }, alpha: 0.85, lifespan: 60000, frequency: 3200, tint: c ?? 0xffffff, advance: 45000 } }),
    confetti: (c) => ({ tex: "lk_square", cfg: { x: { min: 0, max: VIEW_W }, y: -10, speedY: { min: 60, max: 150 }, speedX: { min: -40, max: 40 },
      rotate: { start: 0, end: 720 }, scale: { min: 0.6, max: 1.1 }, lifespan: 6000, frequency: 45,
      tint: c ?? [0xff4d6d, 0xffd23f, 0x3ec1ff, 0x7cff6b, 0xc77dff], advance: 5000 } }),
  };

  function placeUi(scene, z) {
    // HUD text has scrollFactor 0 but still zooms around the camera center: counter-scale so it stays put
    for (const t of [scene.hud, scene.banner, scene.toast]) {
      if (!t) continue;
      if (!t.uiBase) t.uiBase = { x: t.x, y: t.y };
      t.setScale(1 / z).setPosition(VIEW_W / 2 + (t.uiBase.x - VIEW_W / 2) / z, VIEW_H / 2 + (t.uiBase.y - VIEW_H / 2) / z);
    }
  }
  L.uiY = (scene, y) => VIEW_H / 2 + (y - VIEW_H / 2) / (scene.cameras.main.zoom || 1);

  L.applyScene = function (scene, sc) {
    safe("scene", () => {
      if (!scene.sceneFx) L.init(scene);
      sc = sc || {};
      if (sc.background === "moon") sc = { ...sc, sky: sc.sky ?? "#080c22", sky_bottom: sc.sky_bottom ?? "#283459",
        scenery: sc.scenery ?? false, weather: sc.weather && sc.weather.length ? sc.weather : ["stars"],
        weather_color: sc.weather_color ?? "#ffffff", overlay: sc.overlay ?? "#8b91aa", overlay_alpha: sc.overlay_alpha ?? 0.08 };
      else if (sc.background === "dusk") sc = { ...sc, sky: sc.sky ?? "#ffad72", sky_bottom: sc.sky_bottom ?? "#604080",
        scenery: sc.scenery ?? true, scenery_tint: sc.scenery_tint ?? "#75506f", weather: sc.weather && sc.weather.length ? sc.weather : ["clouds"] };
      const st = scene.sceneFx, cam = scene.cameras.main;
      // clear the previous scene look
      for (const k of ["sky", "overlay"]) if (st[k]) { st[k].destroy(); st[k] = null; }
      for (const em of st.weather || []) em.destroy();
      st.weather = [];
      if (st.craters) { st.craters.destroy(); st.craters = null; }
      if (st.cm) st.cm.reset();
      if (st.pix && cam.postFX) { cam.postFX.remove(st.pix); st.pix = null; }

      // sky + background art
      const top = hex(sc.sky) ?? hex(sc.sky_bottom), bottom = hex(sc.sky_bottom) ?? top;
      const bands = scene.bg || [];
      for (const b of bands) {
        b.ts.setVisible(sc.scenery !== false && (!b.isSky || top == null));
        S.recolor(b.ts, hex(sc.scenery_tint));
      }
      if (top != null) {
        st.sky = scene.add.graphics().setScrollFactor(0).setDepth(-11);
        st.sky.fillGradientStyle(top, top, bottom, bottom, 1).fillRect(-VIEW_W, -VIEW_H, VIEW_W * 3, VIEW_H * 3);
        cam.setBackgroundColor(top);
      } else cam.setBackgroundColor("#cfefff");

      // Moonlight turns platform tiles to cool stone and adds pixel-art crater rings to the ground.
      for (const obj of Object.values(scene.byId || {})) {
        if (obj.def && obj.def.type === "platform") for (const v of obj.visuals || []) {
          if (v._moonBase === undefined) v._moonBase = v.recolorColor ?? null;
          S.recolor(v, sc.background === "moon" ? 0x9aa1b4 : v._moonBase);
        }
      }
      if (sc.background === "moon") {
        st.craters = scene.add.graphics().setDepth(1.2);
        st.craters.lineStyle(2, 0x555d70, 0.65);
        for (const e of (scene.level.entities || []).filter((x) => x.type === "platform" && (x.h || 1) > 1)) {
          const left = e.x * scene.TILE + 18, right = (e.x + e.w) * scene.TILE - 12, y = e.y * scene.TILE + 7;
          for (let x = left + 28; x < right; x += 74) {
            st.craters.strokeEllipse(x, y, 18, 7);
            st.craters.strokeEllipse(x + 2, y - 1, 10, 4);
          }
        }
      }

      // color wash over everything
      const ov = hex(sc.overlay);
      if (ov != null && (sc.overlay_alpha ?? 0.3) > 0) {
        st.overlay = scene.add.rectangle(-VIEW_W, -VIEW_H, VIEW_W * 3, VIEW_H * 3, ov, sc.overlay_alpha ?? 0.3)
          .setOrigin(0, 0).setScrollFactor(0).setDepth(9);
      }

      // weather particles, in screen space
      const wc = hex(sc.weather_color);
      for (const w of sc.weather || []) {
        const mk = WEATHER[w];
        if (!mk) continue;
        const { tex, cfg } = mk(wc);
        st.weather.push(scene.add.particles(0, 0, tex, cfg).setScrollFactor(0).setDepth(w === "clouds" ? -9 : 8));
      }

      // whole-screen color filters (WebGL camera post-FX)
      if (cam.postFX) {
        const needCm = (sc.filter && sc.filter !== "none") || sc.hue_shift || sc.saturation || (sc.brightness && sc.brightness !== 1);
        if (needCm) {
          if (!st.cm) st.cm = cam.postFX.addColorMatrix();
          const cm = st.cm;
          const f = sc.filter;
          if (f === "grayscale") cm.grayscale(1, true);
          else if (f === "sepia") cm.sepia(true);
          else if (f === "negative") cm.negative(true);
          else if (f === "vintage") cm.vintagePinhole(true);
          else if (f === "night_vision") { cm.grayscale(1, true); cm.multiply([0.3, 0, 0, 0, 0, 0, 1.5, 0, 0, 0, 0, 0, 0.3, 0, 0, 0, 0, 0, 1, 0], true); }
          if (sc.hue_shift) cm.hue(sc.hue_shift, true);
          if (sc.saturation) cm.saturate(sc.saturation, true);
          if (sc.brightness && sc.brightness !== 1) cm.brightness(sc.brightness, true);
        }
        if (sc.pixelate) st.pix = cam.postFX.addPixelate(Math.round(sc.pixelate));
      }

      // camera zoom (1-2); keep the HUD where it was
      const z = Phaser.Math.Clamp(sc.zoom || 1, 1, 2);
      cam.setZoom(z);
      placeUi(scene, z);
    });
  };

  // ---------- event reactions ----------
  // event: jump, land, step, hurt, die, coin, powerup, stomp, enemy_defeated, win. actor = the object it happened to.
  L.react = function (scene, event, actor, x, y) {
    const list = (scene.level && scene.level.reactions) || [];
    if (!list.length) return;
    safe("reaction", () => {
      for (const r of list) {
        if (r.event !== event) continue;
        const c = hex(r.color), n = r.size || 1, cam = scene.cameras.main;
        const ax = x ?? (actor && actor.x) ?? 0, ay = y ?? (actor && actor.y) ?? 0;
        switch (r.effect) {
          case "shake": cam.shake(160 + 120 * n, 0.006 * n); break;
          case "flash": { const v = c ?? 0xffffff; cam.flash(180, (v >> 16) & 255, (v >> 8) & 255, v & 255); break; }
          case "sparkles": S.fx.sparkle(ax, ay, c ?? 0xfff2a0, Math.round(12 * n)); break;
          case "burst": S.fx.burst(ax, ay, c ?? 0xffffff, Math.round(14 * n)); break;
          case "ring": scene.ring(ax, ay, c ?? 0xffffff, 8 * n); break;
          case "confetti": {
            const em = scene.add.particles(ax, ay, "lk_square", {
              speed: { min: 120, max: 320 * n }, angle: { min: 200, max: 340 }, gravityY: 600, rotate: { start: 0, end: 540 },
              lifespan: 1300, scale: { min: 0.6, max: 1.1 }, emitting: false,
              tint: c != null ? c : [0xff4d6d, 0xffd23f, 0x3ec1ff, 0x7cff6b, 0xc77dff],
            }).setDepth(7);
            em.explode(Math.round(28 * n));
            scene.time.delayedCall(1500, () => em.destroy());
            break;
          }
          case "zoom_bump": {
            if (cam._bumping) break;
            cam._bumping = true;
            const z0 = cam.zoom;
            scene.tweens.add({ targets: cam, zoom: z0 * (1 + 0.06 * n), duration: 110, yoyo: true, ease: "Quad.easeOut",
                               onComplete: () => { cam.setZoom(z0); cam._bumping = false; } });
            break;
          }
          case "spin":
            if (actor && !actor._spinning) {
              actor._spinning = true;
              scene.tweens.add({ targets: actor, angle: { from: 0, to: actor.flipX ? -360 : 360 }, duration: 420 / Math.sqrt(n),
                                 onComplete: () => { actor._spinning = false; actor.setAngle(0); } });
            }
            break;
          case "squash":
            if (actor && !actor._squashing) {
              actor._squashing = true;
              const s0x = actor.scaleX, s0y = actor.scaleY, k = 0.25 * n;
              scene.tweens.add({ targets: actor, scaleX: s0x * (1 + k), scaleY: s0y * (1 - k * 0.8), duration: 90, yoyo: true,
                                 ease: "Quad.easeOut", onUpdate: () => S.fitBody(actor),
                                 onComplete: () => { actor.setScale(s0x, s0y); S.fitBody(actor); actor._squashing = false; } });
            }
            break;
          case "blink":
            if (actor) {
              const ts = actor.visuals || [actor], v = c ?? 0xff3030;
              const prev = ts.map((o) => o.recolorColor ?? null);
              ts.forEach((o) => S.recolor(o, v));
              scene.time.delayedCall(450, () => ts.forEach((o, i) => o.scene && S.recolor(o, prev[i])));
              scene.tweens.add({ targets: ts, alpha: 0.25, duration: 75, yoyo: true, repeat: 2,
                                 onComplete: () => ts.forEach((o) => o.setAlpha(actor.lookAlpha ?? 1)) });
            }
            break;
          case "mark": {
            const by = actor && actor.body ? actor.body.bottom - 2 : ay;
            const m = scene.add.image(ax, by, "lk_print").setTint(c ?? 0x5a3a20).setAlpha(0.7).setDepth(1.5).setScale(n);
            scene.tweens.add({ targets: m, alpha: 0, delay: 1500, duration: 1200, onComplete: () => m.destroy() });
            break;
          }
        }
      }
    });
  };

  window.LOOKS = L;
})();
