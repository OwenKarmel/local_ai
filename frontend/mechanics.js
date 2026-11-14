// mechanics.js — behavior registry. The ONLY file the model is allowed to write.
//
// Each behavior is a function (entity, scene, dt) called every frame for entities
// whose JSON lists it in "behaviors".
//   entity       Phaser sprite with arcade body (entity.body)
//   entity.def   the entity's level JSON
//   entity.props shortcut to entity.def.props (numbers/strings/bools)
//   entity.state per-entity scratch object (persists across frames, reset on restart)
//   scene        the GameScene: scene.player, scene.level, scene.TILE
//   dt           seconds since last frame
window.MECHANICS = window.MECHANICS || {};

// Walk back and forth around the spawn point; turn at walls or range edges.
MECHANICS.patrol = function (entity, scene, dt) {
  const s = entity.state;
  if (s.originX === undefined) { s.originX = entity.x; s.dir = -1; }
  const speed = entity.props.speed ?? 60;
  const range = (entity.props.range ?? 3) * scene.TILE;
  if (entity.body.blocked.left || entity.x < s.originX - range) s.dir = 1;
  else if (entity.body.blocked.right || entity.x > s.originX + range) s.dir = -1;
  entity.body.setVelocityX(speed * s.dir);
  entity.setFlipX(s.dir > 0);
};

// ---------- Abilities (model-written) ----------
// Each ability is an object registered by name:
//   ABILITIES["name"] = { setup(scene) {...}, update(scene, dt) {...} }
// setup runs when the level starts (and after every restart); update runs every frame (dt in seconds).
// game.js runs both inside try/catch; an ability that throws is disabled and reported (window.MECHANICS_ERRORS).
window.ABILITIES = window.ABILITIES || {};

// ---------- Mechanics API (building blocks for model-written abilities) ----------
// Abilities get it as the third argument: setup(scene, api), update(scene, dt, api).
// Added after the raw-Phaser experiment (plan.md): the 4B invented Phaser methods (setLife, isColliding,
// getVelocityX) and the 9B forgot to detect hits. Nothing here is specific to one ability.
// One line per function; the same list goes into the model prompt (backend/mechanics_ref.py).
window.makeMechanicsApi = function (scene, abilityName, report) {
  const guard = (fn) => function (...args) {
    try { return fn.apply(this, args); } catch (err) { report(abilityName, "callback", err); }
  };
  const target = (t) => (t === "player" ? scene.player : t === "enemies" ? scene.enemies : t === "platforms" ? scene.platforms
    : t === "hazards" ? scene.hazards : t);
  const api = {
    TILE: scene.TILE,
    player: scene.player,
    // direction the player faces: 1 = right, -1 = left
    facing: () => (scene.player.flipX ? -1 : 1),
    // keyboard key ("A".."Z", "SPACE", "SHIFT"): k.pressed() true only on the frame it went down; k.down() while held
    key(name) {
      const k = scene.input.keyboard.addKey(String(name).toUpperCase());
      return { pressed: () => Phaser.Input.Keyboard.JustDown(k), down: () => k.isDown };
    },
    // physics sprite. opts: vx, vy (px/s), gravity (default true), tint (0xRRGGBB), scale, bounce (0..1),
    // lifeMs (auto-destroy), solid (collide with platforms, default true). Textures: "fx_ball", "fx_dot", "player", "enemy"
    spawn(texture, x, y, opts = {}) {
      const s = scene.physics.add.sprite(x, y, texture);
      if (opts.scale) s.setScale(opts.scale);
      if (opts.tint != null) s.setTint(opts.tint);
      if (opts.gravity === false) s.body.allowGravity = false;
      if (opts.bounce != null) s.setBounce(opts.bounce);
      s.setVelocity(opts.vx || 0, opts.vy || 0);
      if (opts.solid !== false) scene.physics.add.collider(s, scene.platforms);
      if (opts.lifeMs) scene.time.delayedCall(opts.lifeMs, () => s.active && s.destroy());
      return s;
    },
    // call fn(a, b) when a overlaps b. a, b: a sprite, a group, or "player" | "enemies" | "platforms" | "hazards"
    onHit(a, b, fn) { return scene.physics.add.overlap(target(a), target(b), guard(fn)); },
    // defeat an enemy (same as stomping it): removes it with a burst
    defeat(enemy) {
      if (!enemy || !enemy.active) return;
      if (window.SPRITES && window.SPRITES.fx) window.SPRITES.fx.burst(enemy.x, enemy.y, 0xffffff, 10);
      enemy.disableBody(true, true);
    },
    // active enemy sprites
    enemies: () => scene.enemies.getChildren().filter((e) => e.active),
    // run fn once after ms, or every ms (returns the timer; timer.remove() stops it)
    after: (ms, fn) => scene.time.delayedCall(ms, guard(fn)),
    every: (ms, fn) => scene.time.addEvent({ delay: ms, loop: true, callback: guard(fn) }),
    now: () => scene.time.now,
  };
  return api;
};
