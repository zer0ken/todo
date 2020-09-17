import asyncio
import sys

from decouple import config
from discord import User, DMChannel, Message, Embed, Colour, Activity, ActivityType
from discord.ext.commands import Bot, Context, check, Cooldown, CooldownMapping, BucketType, Command, CommandError, \
    CommandOnCooldown

sys.path.append('.')

NOTHING_TO_DO = 'There is nothing to do now. Try to add some with *`/todo blah blah`*!'
FOOTER = '/todo a I have to wash my hands!'
TODO_MAX_LENGTH = 128


class SharedCooldown(Cooldown):
    def __init__(self, rate, per, type):
        super().__init__(rate, per, type)

    def copy(self):
        return self


class SharedCooldownMapping(CooldownMapping):
    def __init__(self, original):
        super().__init__(original)

    def copy(self):
        return self

    @property
    def cooldwon(self):
        return self._cooldown

    @classmethod
    def from_cooldown(cls, rate, per, type):
        return cls(SharedCooldown(rate, per, type))


def shared_cooldown(rate, per, type=BucketType.default):
    cooldown = SharedCooldown(rate, per, type)
    cooldown_mapping = SharedCooldownMapping(cooldown)

    def decorator(func):
        if isinstance(func, Command):
            func._buckets = cooldown_mapping
        else:
            func.__commands_cooldown__ = cooldown
        return func

    return decorator


def tokens_len(count: tuple or int):
    if type(count) != tuple:
        count = (count,)

    def predicate(ctx: Context) -> bool:
        return len(ctx.message.content.split()) in count

    return check(predicate)


class TodoEmbed(Embed):
    def __init__(self, **kwargs):
        super().__init__(title=':white_check_mark: Todo list of **', colour=Colour.from_rgb(119, 178, 85), **kwargs)
        self.set_footer(text=FOOTER)

    @staticmethod
    def from_embed(origin: Embed):
        return TodoEmbed(description=origin.description)

    def set_author_(self, user: User):
        self.title += str(user) + '**'
        self.set_thumbnail(url=user.avatar_url)


bot = Bot('/', None, case_insensitive=True)
todo_cooldown = shared_cooldown(1, 1, type=BucketType.user)


def add_todo(embed: Embed, content: str):
    todos = [r'\* ' + content]
    if embed.description:
        todos.extend(embed.description.split('\n'))
    embed.description = '\n'.join([r'\* ' + line[3:] for line in todos])


def remove_todo(embed: TodoEmbed, key: str) -> str:
    todos = list(reversed(embed.description.split('\n')))
    removed = r'\*  '
    for i, line in enumerate(todos):
        if key in line:
            removed = todos.pop(i)
            break
    if removed[3:]:
        embed.description = '\n'.join([r'\* ' + line[3:] for line in reversed(todos)])
    return removed[3:]


def get_todo_embed(message: Message):
    if message is None:
        return TodoEmbed()
    for e in message.embeds:
        if e.footer and e.footer.text == FOOTER:
            return TodoEmbed.from_embed(e)
    return TodoEmbed()


async def get_message(user: User):
    channel: DMChannel = user.dm_channel
    if channel is None:
        channel = await user.create_dm()
    message = await channel.history().find(
        lambda m: m.author == bot.user and get_todo_embed(m) is not None)
    if message is None:
        message = await channel.history().find(lambda m: m.author == bot.user)
    return message


async def clear_messages(user: User):
    channel: DMChannel = user.dm_channel
    if channel is None:
        channel = await user.create_dm()
    while message := await channel.history(oldest_first=True).find(lambda m: m.author == bot.user):
        await message.delete()


async def update_todo(todo_embed: TodoEmbed, ctx: Context, content: str = None):
    data_message = await get_message(ctx.author)
    todo_embed.set_author_(ctx.author)
    tasks = list()
    if todo_embed.description:
        if ctx.guild is None:
            tasks.append(ctx.send(embed=todo_embed))
            if data_message is not None:
                tasks.append(data_message.delete())
        else:
            tasks.append(ctx.send(content=content, embed=todo_embed, delete_after=60))
            if data_message is None:
                tasks.append(ctx.author.send(content, embed=todo_embed))
            else:
                tasks.append(data_message.edit(embed=todo_embed))
    elif ctx.guild is None:
        tasks.append(ctx.send(NOTHING_TO_DO))
        if data_message is not None:
            tasks.append(data_message.delete())
    else:
        tasks.append(ctx.send(NOTHING_TO_DO, delete_after=60))
        if data_message is not None:
            tasks.append(data_message.delete())
    await asyncio.wait(tasks)


@bot.group(name='todo', aliases=('투두', '할일'), invoke_without_command=True)
@todo_cooldown
async def todo(ctx: Context, *, content: str = ''):
    if content:
        await todo_add(ctx, content=content)
    else:
        await todo_list(ctx)


@todo.command(name='+', aliases=('add', 'a', '추가'))
@todo_cooldown
async def todo_add(ctx: Context, *, content: str):
    if len(content) > TODO_MAX_LENGTH:
        await ctx.send(f'Content is too long!!! You have to send a content shorter than {TODO_MAX_LENGTH} characters.')
        return
    data_message = await get_message(ctx.author)
    todo_embed = get_todo_embed(data_message)
    add_todo(todo_embed, content)
    if len(todo_embed.description) > 2048:
        await ctx.send('Your todo list is now full... just remove some to add new one!')
        return
    await update_todo(todo_embed, ctx, f'Added `{content}` to your todo list!')


@todo.command(name='?', aliases=('list', 'l', '목록'))
@tokens_len(2)
@todo_cooldown
async def todo_list(ctx: Context):
    data_message = await get_message(ctx.author)
    await update_todo(get_todo_embed(data_message), ctx)


@todo.command(name='-', aliases=('remove', 'r', '삭제'))
@todo_cooldown
async def todo_remove(ctx: Context, *, key: str):
    data_message = await get_message(ctx.author)
    todo_embed = get_todo_embed(data_message)
    removed = remove_todo(todo_embed, key)
    if removed:
        await ctx.send(f'Removed `{removed}`!')
        await update_todo(todo_embed, ctx)
    else:
        await ctx.send(f'task about `{key}` is not found.')


@todo.command(name='clear', aliases=('초기화',))
@todo_cooldown
async def todo_clear(ctx: Context):
    message = await ctx.send('Clearing your todo list...')
    await clear_messages(ctx.author)
    await message.edit(content='Cleared your todo list!')
    await update_todo(TodoEmbed(), ctx)


@todo.command(name='help', aliases=('도움말',))
async def todo_help(ctx: Context):
    help = '***`/todo help`*** to check how to use this bot.\n' \
           '***`/todo`***, ***`/todo l`***, or ***`/todo list`*** to see your todo list.\n' \
           '***`/todo <task>`***, ***`/todo a <task>`*** or ***`/todo add <task>`*** to add new task to do.\n' \
           '***`/todo r <words>`*** or ***`/todo remove <words>`*** to remove task you have done or canceled. ' \
           'it will search through your todo list to find tasks including `words` and remove the oldest one.\n' \
           '***`/todo clear`*** to clear your todo list. **!!! IT CAN NOT BE RESTORED !!!**'
    await ctx.send(help)


async def on_command_error(context: Context, exception: CommandError):
    if isinstance(exception, CommandOnCooldown):
        await context.send('You\'re on cooldown now. Wait {:.2} seconds.'.format(exception.retry_after))
        return
    raise exception


async def on_ready():
    await bot.change_presence(activity=Activity(type=ActivityType.watching, name='/todo help'))


bot.add_listener(on_command_error)
bot.add_listener(on_ready)


if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(bot.start(config('TOKEN')))

