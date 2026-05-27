const DIR_UP = 0;
const DIR_RIGHT = 1;
const DIR_DOWN = 2;
const DIR_LEFT = 3;

const DIR_VECTORS = [
  { dx: 0, dy: -1 },
  { dx: 1, dy: 0 },
  { dx: 0, dy: 1 },
  { dx: -1, dy: 0 },
];

const TANK_SIZE = 38;
const PLAYER_SPEED = 2.8;
const ENEMY_SPEED = 1.6;
const SHOOT_COOLDOWN_FRAMES = 30; // ~0.5s at 60fps

class Tank {
  constructor(x, y, direction, isPlayer, color, barrelColor) {
    this.x = x;
    this.y = y;
    this.width = TANK_SIZE;
    this.height = TANK_SIZE;
    this.direction = direction;
    this.speed = isPlayer ? PLAYER_SPEED : ENEMY_SPEED;
    this.hp = 3;
    this.alive = true;
    this.isPlayer = isPlayer;
    this.color = color;
    this.barrelColor = barrelColor;
    this.shootCooldown = 0;
  }

  get cx() { return this.x + this.width / 2; }
  get cy() { return this.y + this.height / 2; }

  move(dir) {
    this.direction = dir;
    const v = DIR_VECTORS[dir];
    this.x += v.dx * this.speed;
    this.y += v.dy * this.speed;
  }

  undoMove(dir) {
    const v = DIR_VECTORS[dir];
    this.x -= v.dx * this.speed;
    this.y -= v.dy * this.speed;
  }

  canShoot() {
    return this.alive && this.shootCooldown <= 0;
  }

  shoot() {
    if (!this.canShoot()) return null;
    this.shootCooldown = SHOOT_COOLDOWN_FRAMES;
    const v = DIR_VECTORS[this.direction];
    const bx = this.cx - 3 + v.dx * (this.width / 2 + 2);
    const by = this.cy - 3 + v.dy * (this.height / 2 + 2);
    return new Bullet(bx, by, this.direction, this.isPlayer);
  }

  takeDamage() {
    this.hp -= 1;
    if (this.hp <= 0) {
      this.hp = 0;
      this.alive = false;
    }
  }

  update() {
    if (this.shootCooldown > 0) this.shootCooldown -= 1;
  }

  draw(ctx) {
    if (!this.alive) return;
    const { x, y, width: w, height: h, direction: dir, color, barrelColor } = this;
    ctx.save();
    ctx.translate(x + w / 2, y + h / 2);
    const angle = dir * Math.PI / 2;
    ctx.rotate(angle);

    // Treads
    ctx.fillStyle = '#333';
    ctx.fillRect(-w / 2, -h / 2, w / 5, h);
    ctx.fillRect(w / 2 - w / 5, -h / 2, w / 5, h);

    // Body
    ctx.fillStyle = color;
    ctx.fillRect(-w / 2 + w / 5, -h / 2 + 2, w * 3 / 5 - 4, h - 4);

    // Barrel
    ctx.fillStyle = barrelColor;
    ctx.fillRect(-3, -h / 2 - 6, 6, h / 2 + 4);

    ctx.restore();
  }
}
