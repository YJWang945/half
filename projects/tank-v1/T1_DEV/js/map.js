const COLS = 20;
const ROWS = 15;
const CELL = 40;

const TILE_EMPTY = 0;
const TILE_BRICK = 1;
const TILE_STEEL = 2;

const MAP_DATA = [
  [2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2],
  [2,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2],
  [2,0,0,1,1,0,0,1,1,0,0,1,1,0,0,1,1,0,0,2],
  [2,0,0,1,1,0,0,1,1,0,0,1,1,0,0,1,1,0,0,2],
  [2,0,0,1,1,0,0,1,1,0,0,1,1,0,0,1,1,0,0,2],
  [2,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2],
  [2,0,0,0,0,0,0,0,0,1,1,0,0,0,0,0,0,0,0,2],
  [2,0,0,1,0,0,1,0,0,1,1,0,0,1,0,0,1,0,0,2],
  [2,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2],
  [2,0,0,0,0,0,1,1,0,0,0,1,1,0,0,0,0,0,0,2],
  [2,0,0,1,1,0,0,0,0,0,0,0,0,0,1,1,0,0,0,2],
  [2,0,0,1,1,0,0,0,0,0,0,0,0,0,1,1,0,0,0,2],
  [2,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2],
  [2,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2],
  [2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2],
];

function getTile(col, row) {
  if (col < 0 || col >= COLS || row < 0 || row >= ROWS) return TILE_STEEL;
  return MAP_DATA[row][col];
}

function setTile(col, row, value) {
  if (col >= 0 && col < COLS && row >= 0 && row < ROWS) {
    MAP_DATA[row][col] = value;
  }
}

function drawMap(ctx) {
  for (let row = 0; row < ROWS; row++) {
    for (let col = 0; col < COLS; col++) {
      const tile = MAP_DATA[row][col];
      const x = col * CELL;
      const y = row * CELL;
      if (tile === TILE_BRICK) {
        ctx.fillStyle = '#b5651d';
        ctx.fillRect(x + 1, y + 1, CELL - 2, CELL - 2);
        ctx.fillStyle = '#8b4513';
        ctx.fillRect(x + 4, y + 4, CELL / 2 - 4, CELL / 2 - 4);
        ctx.fillRect(x + CELL / 2, y + CELL / 2, CELL / 2 - 4, CELL / 2 - 4);
      } else if (tile === TILE_STEEL) {
        ctx.fillStyle = '#777';
        ctx.fillRect(x + 1, y + 1, CELL - 2, CELL - 2);
        ctx.fillStyle = '#aaa';
        ctx.fillRect(x + 2, y + 2, CELL - 4, CELL - 4);
        ctx.fillStyle = '#555';
        ctx.fillRect(x + 6, y + 6, CELL - 12, CELL - 12);
      }
    }
  }
}

function getWallRects() {
  const rects = [];
  for (let row = 0; row < ROWS; row++) {
    for (let col = 0; col < COLS; col++) {
      if (MAP_DATA[row][col] !== TILE_EMPTY) {
        rects.push({
          x: col * CELL,
          y: row * CELL,
          w: CELL,
          h: CELL,
          isSteel: MAP_DATA[row][col] === TILE_STEEL,
        });
      }
    }
  }
  return rects;
}
