// mechanics.js — behavior registry. The ONLY file the model is allowed to write.
//
// Each behavior is a function (entity, scene, dt) called every frame for entities
// whose JSON lists it in "behaviors".
//   entity       Phaser sprite with arcade body (entity.body)
//   entity.def   the entity's level JSON
//   entity.props shortcut to entity.def.props (numbers/strings/bools)
//   entity.state per-entity scratch object (persists across frames, reset on restart)
//   scene        the GameScene: scene.player, scene.level, scene.TILE,
//                scene.isBig / scene.setPlayerBig(on) (taller player with a different look that survives one hit),
//                scene.hurt(reason) (shrinks a big player, otherwise kills),
//                scene.enemyHp(e) / scene.damageEnemy(e, n) / scene.defeatEnemy(e) (enemies take props.hp hits),
//                scene.spawnEnemyShot(x, y, vx, vy, {sprite, tint}) (projectile that hurts the player),
//                scene.solidAt(px, py) (is this world point inside a platform?),
//                scene.showToast(text), scene.ring(x, y, color, size), scene.cameras.main.shake(ms, amount)
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

// Two-phase boss. Walks its platform (turns at walls and ledges) and hops every props.jump_every seconds.
// Phase 2 starts once its hp left (scene.enemyHp) drops to props.phase2_at: it turns red, walks at
// props.phase2_speed and shoots at the player every props.shoot_every seconds. Every prop can change live.
MECHANICS.boss = function (entity, scene, dt) {
  const s = entity.state, p = entity.props, b = entity.body;
  if (s.dir === undefined) { s.dir = -1; s.hopT = 0; s.shotT = 0; s.phase = 1; }
  const phase = scene.enemyHp(entity) <= (p.phase2_at ?? 0) ? 2 : 1;
  if (phase !== s.phase) {
    s.phase = phase;
    if (phase === 2) {
      entity.setTint(0xff6a5a);
      scene.cameras.main.shake(350, 0.01);
      scene.ring(entity.x, entity.y, 0xff6a5a, 14);
      scene.showToast(`${entity.def.id}: phase 2!`);
      if (b.blocked.down) b.setVelocityY(-480); // angry leap
    } else {
      SPRITES.applyTint(entity, entity.look, entity.def.tint); // hp raised live: back to phase 1 colors
    }
  }

  const onGround = b.blocked.down;
  if (b.blocked.left) s.dir = 1;
  else if (b.blocked.right) s.dir = -1;
  else if (onGround && !scene.solidAt(s.dir > 0 ? b.right + 4 : b.left - 4, b.bottom + 4)) s.dir = -s.dir; // ledge ahead

  const every = p.jump_every ?? 0;
  s.hopT += dt;
  if (every > 0 && s.hopT >= every && onGround) { s.hopT = 0; b.setVelocityY(-420); }

  const shootEvery = p.shoot_every ?? 0;
  if (phase === 2 && shootEvery > 0) {
    s.shotT += dt;
    if (s.shotT >= shootEvery) {
      s.shotT = 0;
      const pl = scene.player, dx = pl.x - entity.x, dy = pl.y - entity.y, d = Math.hypot(dx, dy) || 1;
      const v = p.shot_speed ?? 260;
      scene.spawnEnemyShot(entity.x + Math.sign(dx || 1) * (b.width / 2 + 6), entity.y - 6, (dx / d) * v, (dy / d) * v);
    }
  }

  b.setVelocityX((phase === 2 ? p.phase2_speed ?? 140 : p.speed ?? 70) * s.dir);
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
