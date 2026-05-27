const BULLET_SPEED = 6;
const BULLET_SIZE = 6;

class Bullet {
  constructor(x, y, direction, isFriendly) {
    this.x = x;
    this.y = y;
    this.width = BULLET_SIZE;
    this.height = BULLET_SIZE;
    this.direction = direction;
    this.speed = BULLET_SPEED;
    this.alive = true;
    this.isFriendly = isFriendly;
  }

  update(mapWalls) {
    const v = DIR_VECTORS[this.direction];
    this.x += v.dx * this.speed;
    this.y += v.dy * this.speed;

    // Check wall collision
    for (const wall of mapWalls) {
      if (rectCollide(this, wall)) {
        this.alive = false;
        if (!wall.isSteel) {
          const col = Math.floor(wall.x / CELL);
          const row = Math.floor(wall.y / CELL);
          setTile(col, row, TILE_EMPTY);
        }
        return;
      }
    }

    // Out of bounds
    if (this.x < -10 || this.x > 810 || this.y < -10 || this.y > 610) {
      this.alive = false;
    }
  }

  draw(ctx) {
    if (!this.alive) return;
    ctx.fillStyle = this.isFriendly ? '#ff4' : '#f66';
    ctx.shadowColor = this.isFriendly ? '#ff0' : '#f00';
    ctx.shadowBlur = 6;
    ctx.fillRect(this.x, this.y, this.width, this.height);
    ctx.shadowBlur = 0;
  }
}
