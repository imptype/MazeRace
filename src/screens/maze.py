import time
import discohook
import numpy as np

def get_valid_moves(maze_grid, position): # returns disabled true/false for left, right, up, down
  border = len(maze_grid) - 1
  y, x = position
  left_disabled = x == 0 or bool(maze_grid[y][x - 1])
  right_disabled = x == border or bool(maze_grid[y][x + 1])
  up_disabled = y == 0 or bool(maze_grid[y - 1][x])
  down_disabled = y == border or bool(maze_grid[y + 1][x])
  return left_disabled, right_disabled, up_disabled, down_disabled

async def before_move_check(interaction): # stop processing if timed out already or not maze owner
  data = interaction.payload['message']['components'][0]['components'][0]['custom_id'].split(':')[2:]
  maze_id = data[0]
  position = list(map(int, data[1:3]))
  end = list(map(int, data[3:5]))
  timeout = int(data[5])
  level = int(data[6])
  user_id = data[7]

  # check if this maze is already over
  if time.time() > timeout:
    embed = interaction.message.embeds[0]
    embed.set_image('attachment://maze.png')
    embed.description = 'Times up. You did not finish the maze.'
    await interaction.response.update_message(embed = embed, view = None)
    await interaction.client.db.check_maze_finished(maze_id)
    return
    
  # check if they are maze owner
  if user_id != interaction.author.id: # after, lets them update the maze if it ended
    await interaction.response.send('This is not your maze.', ephemeral = True)
    return
  
  return maze_id, position, end, timeout, level, user_id

async def move(interaction, x, y):
  data = await before_move_check(interaction)
  if not data:
    return
  
  maze_id, position, end, timeout, level, user_id = data
  app = interaction.client
  helpers = app.helpers

  # draw maze background first if not cached
  maze_data = app.mazes.get(maze_id)
  if not maze_data:
    record = await app.db.get_maze(maze_id) # server reloaded

    if not record: # maze was already finished
      embed = interaction.message.embeds[0]
      embed.set_image('attachment://maze.png')
      embed.description = 'Timed out. You did not finish the maze.'
      return await interaction.response.update_message(embed = embed, view = None)

    maze_data = await helpers.draw_maze(np.array(record['grid']), tuple(record['start']), tuple(record['end']))
    app.mazes[maze_id] = maze_data

  # calculate steps below, this can probably be simplified in the future
  grid = maze_data[0]
  border = len(grid) - 1
  steps = 0

  if x == -1:
    text = 'left'
    # while True:
    #   if not position[0]: # touching left border
    #     break
    #   elif not grid[position[0]-1, position[1]]: # tile ahead of that is a wall
    #     print(grid[position[0]-1, position[1]])
    #     break
    #   elif steps: # only if you moved already
    #     if position[1]: # if ur not touching bottom border
    #       if not grid[position[0], position[1]-1]: # stop if path tile is below
    #         break
    #     if position[1] != border: # etc
    #       if not grid[position[0], position[1]+1]:
    #         break
    position[1] -= 1
    #steps += 1

  elif x == 1:
    text = 'right'
    position[1] += 1

  elif y == 1:
    text = 'down'
    position[0] += 1

  elif y == -1:
    text = 'up'
    position[0] -= 1

  else:
    raise ValueError('Bad move input', x, y)

  image = await helpers.draw_player_on_maze(app, maze_data, tuple(position), interaction.author, level) # numpy uses position tuple index

  embed = interaction.message.embeds[0]
  embed.set_image(image)

  # if win, stop the view otherwise send an update
  if position == end:
    embed = interaction.message.embeds[0]
    seconds = helpers.level_to_seconds(level)
    started_at = timeout - seconds
    time_taken = round(time.time() - started_at, 2)
    embed.description = 'You finished in `{:.2f}s`!'.format(time_taken)
    await interaction.response.update_message(embed = embed, view = None, file = image)
    await app.db.update_maze(maze_id, user_id, time_taken)
    return
  
  embed.description = 'You moved {}. Maze ends <t:{}:R>.'.format(text, timeout)
  
  await MazeView(interaction, 1, data = (maze_id, position, end, timeout, level, user_id, embed, image)).update()

@discohook.button.new(emoji = '⬅️', custom_id = 'left:v0.0')
async def left_button(interaction):
  await move(interaction, -1, 0)

@discohook.button.new(emoji = '➡️', custom_id = 'right:v0.0')
async def right_button(interaction):
  await move(interaction, 1, 0)

@discohook.button.new(emoji = '⬆️', custom_id = 'up:v0.0')
async def up_button(interaction):
  await move(interaction, 0, -1) # pillow draws from top left, so this is negative

@discohook.button.new(emoji = '⬇️', custom_id = 'down:v0.0')
async def down_button(interaction):
  await move(interaction, 0, 1)

@discohook.button.new('Give Up', emoji = '🏳️', style = discohook.ButtonStyle.red, custom_id = 'giveup:v0.0')
async def giveup_button(interaction):
  data = await before_move_check(interaction)
  if not data:
    return

  maze_id = data[0]
  
  embed = interaction.message.embeds[0]
  embed.set_image('attachment://maze.png')
  embed.description = 'You gave up.'
  await interaction.response.update_message(embed = embed, view = None)
  await interaction.client.db.update_maze(maze_id, interaction.author.id, 0)

class MazeView(discohook.View):
  def __init__(self, interaction = None, flag = None, data = None):
    super().__init__()

    if interaction:
      self.interaction = interaction
      
      if not flag: # race begin
        maze_id, start, end, timeout, level, user_id, embed, image = data
        
        self.content = '<@{}>'.format(user_id)
        self.embed = embed
        self.image = image

        position = start

      elif flag == 1: # update position (clicked a button)
        maze_id, position, end, timeout, level, user_id, embed, image = data

        self.embed = embed
        self.image = image
      
      else:
        raise ValueError('Unhandled MazeView flag', flag)

      data = ':{}:{}:{}:{}:{}:{}:{}:{}'.format(maze_id, *position, *end, timeout, level, user_id) # stuff all these values in a custom id
      # 9 + 1 + 16 + 1 + 2 + 1 + 2 + 1 + 2 + 1 + 2 + 1 + 10 + 1 + 2 + 19 = 71, still 29 chars left
    
      maze_grid = interaction.client.mazes[maze_id][0]
      left_disabled, right_disabled, up_disabled, down_disabled = get_valid_moves(maze_grid, position)

      dynamic_left_button = discohook.Button(
        emoji = left_button.emoji,
        custom_id = left_button.custom_id + data,
        disabled = left_disabled
      )

      dynamic_right_button = discohook.Button(
        emoji = right_button.emoji,
        custom_id = right_button.custom_id + ':', # this is so it doesn't overwrite the actual callback
        disabled = right_disabled
      )

      dynamic_up_button = discohook.Button(
        emoji = up_button.emoji,
        custom_id = up_button.custom_id + ':',
        disabled = up_disabled
      )

      dynamic_down_button = discohook.Button(
        emoji = down_button.emoji,
        custom_id = down_button.custom_id + ':',
        disabled = down_disabled
      )
      
      self.add_buttons(dynamic_left_button, dynamic_right_button, dynamic_up_button, dynamic_down_button, giveup_button)

    else: # persistent
      self.add_buttons(left_button, right_button, up_button, down_button, giveup_button)

  async def followup(self): # for race begin only
    await self.interaction.response.followup(self.content, embed = self.embed, view = self, file = self.image)

  async def update(self): # for race begin only
    await self.interaction.response.update_message(embed = self.embed, view = self, file = self.image)