const express = require('express');
const app = express();

app.get('/ping', (req, res) => {
  res.json({ message: 'pong' });
});

const PORT = process.env.PORT;
console.log('process.env.PORT:', process.env.PORT);
if (!PORT) {
  console.error('PORT is not set!');
  process.exit(1);
}
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});