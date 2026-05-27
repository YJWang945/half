function rectCollide(a, b) {
  return (
    a.x < b.x + b.w &&
    a.x + (a.width || a.w) > b.x &&
    a.y < b.y + b.h &&
    a.y + (a.height || a.h) > b.y
  );
}

function resolveTankWallCollision(tank, walls) {
  for (const wall of walls) {
    if (rectCollide(tank, wall)) {
      return true;
    }
  }
  return false;
}

function resolveTankCollision(tank, otherTank) {
  if (!otherTank.alive) return false;
  if (tank === otherTank) return false;
  return rectCollide(tank, otherTank);
}

function bulletHitsTank(bullet, tank) {
  if (!bullet.alive || !tank.alive) return false;
  return rectCollide(bullet, tank);
}
