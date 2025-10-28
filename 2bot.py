import discord
from discord import app_commands
import json
import os
import asyncio
import re
from flask import Flask
from collections import defaultdict
from datetime import datetime, timedelta
import threading

# ===== НАСТРОЙКА БОТА =====
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

class MyBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        print("✅ Слеш-команды синхронизированы")

bot = MyBot()

# ===== СИСТЕМА МОДЕРАЦИИ PHANTOM VORTEX =====
class PhantomVortexModSystem:
    def __init__(self):
        self.user_warnings = defaultdict(int)
        self.warning_timestamps = defaultdict(list)
        self.spam_detection = defaultdict(list)
    
    async def analyze_message(self, message):
        if message.author.bot:
            return None
        
        violations = []
        
        # Уровень 4: Критические нарушения
        if await self.check_level4_violations(message):
            return "LEVEL4"
        
        # Уровень 3: Серьезные нарушения
        if await self.check_level3_violations(message):
            violations.append("LEVEL3")
        
        # Уровень 2: Средние нарушения
        if await self.check_level2_violations(message):
            violations.append("LEVEL2")
        
        # Уровень 1: Легкие нарушения
        if await self.check_level1_violations(message):
            violations.append("LEVEL1")
        
        return violations[0] if violations else None
    
    async def check_level4_violations(self, message):
        content = message.content.lower()
        threats = ['убью', 'зарежу', 'изобью', 'вешайся', 'суицид', 'сдохни']
        discrimination = ['нигер', 'ниггер', 'чурка', 'хач', 'жид', 'пидорас']
        
        if (any(threat in content for threat in threats) or 
            any(disc_word in content for disc_word in discrimination) or
            re.search(r'\b\d{11,}\b', content)):
            return True
        return False
    
    async def check_level3_violations(self, message):
        content = message.content.lower()
        personal_insults = ['мудак', 'мудила', 'дебил', 'долбоёб', 'ублюдок', 'говноед']
        advertising = ['подписывайся', 'мой канал', 'купить', 'продам', 'реклама']
        
        if (any(insult in content for insult in personal_insults) or
            any(ad in content for ad in advertising) or
            await self.detect_targeted_trolling(message)):
            return True
        return False
    
    async def check_level2_violations(self, message):
        content = message.content.lower()
        nsfw_words = ['секс', 'порно', 'голый', 'обнаженный']
        cheat_words = ['читы', 'читер', 'взлом', 'паблик чит']
        mentions = message.mentions + message.role_mentions
        
        if (any(nsfw in content for nsfw in nsfw_words) or
            any(cheat in content for cheat in cheat_words) or
            len(mentions) >= 3):
            return True
        return False
    
    async def check_level1_violations(self, message):
        if await self.detect_spam(message) or await self.detect_off_topic(message):
            return True
        return False
    
    async def detect_spam(self, message):
        user_id = message.author.id
        now = datetime.now()
        self.spam_detection[user_id].append(now)
        self.spam_detection[user_id] = [t for t in self.spam_detection[user_id] if now - t < timedelta(seconds=10)]
        return len(self.spam_detection[user_id]) >= 5
    
    async def detect_targeted_trolling(self, message):
        if message.reference:
            try:
                replied_msg = await message.channel.fetch_message(message.reference.message_id)
                if replied_msg.author != message.author:
                    negative_words = ['дурак', 'идиот', 'тупой', 'слабый']
                    return any(word in message.content.lower() for word in negative_words)
            except:
                pass
        return False
    
    async def detect_off_topic(self, message):
        channel_name = message.channel.name.lower()
        if 'музыка' in channel_name and not await self.is_music_related(message.content):
            return True
        return False
    
    async def is_music_related(self, content):
        music_words = ['песня', 'трек', 'альбом', 'музыка', 'слушать']
        return any(word in content.lower() for word in music_words)
    
    async def apply_punishment(self, user, violation_level, channel, reason=""):
        user_id = user.id
        now = datetime.now()
        
        self.warning_timestamps[user_id].append(now)
        self.warning_timestamps[user_id] = [t for t in self.warning_timestamps[user_id] if now - t < timedelta(days=10)]
        active_warns = len(self.warning_timestamps[user_id])
        
        log_channel = discord.utils.get(channel.guild.channels, name="📋-логи-модерации")
        if not log_channel:
            overwrites = {channel.guild.default_role: discord.PermissionOverwrite(read_messages=False)}
            log_channel = await channel.guild.create_text_channel("📋-логи-модерации", overwrites=overwrites)
        
        embed = discord.Embed(title="🚨 Нарушение правил", color=0xe74c3c, timestamp=now)
        embed.add_field(name="Участник", value=user.mention, inline=True)
        embed.add_field(name="Уровень", value=violation_level, inline=True)
        embed.add_field(name="Активные варны", value=f"{active_warns}/3", inline=True)
        embed.add_field(name="Причина", value=reason or "Автомодерация", inline=False)
        
        if violation_level == "LEVEL4":
            try:
                await user.ban(reason=f"Критическое нарушение: {reason}")
                embed.add_field(name="Наказание", value="🔨 Пермабан", inline=False)
            except:
                embed.add_field(name="Ошибка", value="Не удалось забанить", inline=False)
        
        elif violation_level == "LEVEL3":
            for _ in range(2):
                self.warning_timestamps[user_id].append(now)
            try:
                await user.timeout(timedelta(days=3), reason=f"Серьезное нарушение: {reason}")
                embed.add_field(name="Наказание", value="🔇 Мут 3 дня + 2 варна", inline=False)
            except:
                embed.add_field(name="Наказание", value="2 варна", inline=False)
        
        elif violation_level == "LEVEL2":
            try:
                await user.timeout(timedelta(hours=6), reason=f"Среднее нарушение: {reason}")
                embed.add_field(name="Наказание", value="🔇 Мут 6 часов + варн", inline=False)
            except:
                embed.add_field(name="Наказание", value="1 варн", inline=False)
        
        elif violation_level == "LEVEL1":
            embed.add_field(name="Наказание", value="⚠️ Предупреждение", inline=False)
        
        if active_warns >= 3:
            try:
                await user.ban(reason="Автобан: 3 активных предупреждения")
                embed.add_field(name="🔨 Автобан", value="3 активных варна", inline=False)
            except:
                pass
        
        await log_channel.send(embed=embed)
        
        if violation_level in ["LEVEL2", "LEVEL3", "LEVEL4"]:
            await channel.send(f"🚨 {user.mention} получил наказание. Детали в {log_channel.mention}")

mod_system = PhantomVortexModSystem()

# ===== СИСТЕМА СОХРАНЕНИЯ КОМАНД =====
def load_teams():
    if os.path.exists('teams.json'):
        try:
            with open('teams.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_teams():
    with open('teams.json', 'w', encoding='utf-8') as f:
        json.dump(registered_teams, f, ensure_ascii=False, indent=2)

def migrate_teams_data():
    """Конвертирует старые данные в новый формат"""
    global registered_teams
    migrated = False
    
    for user_id, data in list(registered_teams.items()):
        if isinstance(data, str):  # Старый формат
            registered_teams[user_id] = {
                'team_name': data,
                'captain': 'Не указан',
                'game': 'dota 2'
            }
            migrated = True
        elif isinstance(data, dict) and 'game' not in data:
            registered_teams[user_id]['game'] = 'dota 2'
            registered_teams[user_id]['captain'] = data.get('captain', 'Не указан')
            migrated = True
    
    if migrated:
        save_teams()
        print("✅ Данные мигрированы в новый формат")

registered_teams = load_teams()
migrate_teams_data()

# ===== СИСТЕМА ПРИГЛАШЕНИЙ =====
class TeamMemberSelect(discord.ui.UserSelect):
    def __init__(self, team_role_id):
        super().__init__(placeholder="Выберите участников команды...", max_values=4)
        self.team_role_id = team_role_id
    
    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(self.team_role_id)
        for user in self.values:
            await user.add_roles(role)
        
        await interaction.response.send_message(
            f"✅ Приглашены в команду: {', '.join([user.mention for user in self.values])}",
            ephemeral=True
        )

class OpponentMemberSelect(discord.ui.UserSelect):
    def __init__(self, opponent_role_id):
        super().__init__(placeholder="Выберите противников...", max_values=5)
        self.opponent_role_id = opponent_role_id
    
    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(self.opponent_role_id)
        for user in self.values:
            await user.add_roles(role)
        
        await interaction.response.send_message(
            f"🆚 Приглашены противники: {', '.join([user.mention for user in self.values])}",
            ephemeral=True
        )

class TeamInviteView(discord.ui.View):
    def __init__(self, team_role_id):
        super().__init__(timeout=60)
        self.team_role_id = team_role_id
        self.add_item(TeamMemberSelect(team_role_id))

class OpponentInviteView(discord.ui.View):
    def __init__(self, opponent_role_id):
        super().__init__(timeout=60)
        self.opponent_role_id = opponent_role_id
        self.add_item(OpponentMemberSelect(opponent_role_id))

class ClashInviteView(discord.ui.View):
    def __init__(self, team_role_id, opponent_role_id, team_name):
        super().__init__(timeout=None)
        self.team_role_id = team_role_id
        self.opponent_role_id = opponent_role_id
        self.team_name = team_name
    
    @discord.ui.button(label='➕ Пригласить свою команду', style=discord.ButtonStyle.success, custom_id='invite_team_btn')
    async def invite_team(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            f"**👥 Пригласите свою команду:**\n"
            f"Участники получат роль <@&{self.team_role_id}>\n"
            f"И смогут зайти в ваш клоз!",
            view=TeamInviteView(self.team_role_id),
            ephemeral=True
        )
    
    @discord.ui.button(label='🆚 Пригласить противников', style=discord.ButtonStyle.danger, custom_id='invite_opponents_btn')
    async def invite_opponents(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            f"**🆚 Пригласите противников:**\n"
            f"Они получат роль <@&{self.opponent_role_id}>\n"
            f"И смогут зайти в канал противников!",
            view=OpponentInviteView(self.opponent_role_id),
            ephemeral=True
        )

# ===== МОДАЛЬНЫЕ ОКНА И ФУНКЦИИ =====
class RegistrationModal(discord.ui.Modal, title='📝 Регистрация команды'):
    team_name = discord.ui.TextInput(label='Название команды', placeholder='Введите название команды...', max_length=50)
    captain_name = discord.ui.TextInput(label='Имя капитана', placeholder='Ваш игровой никнейм...', max_length=30)
    game_choice = discord.ui.TextInput(
        label='Игра (Dota 2 / CS2)', 
        placeholder='Напишите Dota 2 или CS2...', 
        max_length=10
    )

    async def on_submit(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        
        # Проверяем корректность выбора игры
        game = self.game_choice.value.strip().lower()
        if game not in ['dota 2', 'cs2']:
            await interaction.response.send_message(
                "❌ Неверная игра! Выберите: **Dota 2** или **CS2**", 
                ephemeral=True
            )
            return
        
        if user_id in registered_teams:
            await interaction.response.send_message(
                f"❌ Вы уже зарегистрированы как **{registered_teams[user_id]['team_name']}**!", 
                ephemeral=True
            )
            return
        
        # Сохраняем данные команды
        registered_teams[user_id] = {
            'team_name': self.team_name.value,
            'captain': self.captain_name.value,
            'game': game
        }
        save_teams()
        
        embed = discord.Embed(
            title="✅ Регистрация завершена!", 
            description=f"Команда **{self.team_name.value}** зарегистрирована!", 
            color=0x2ecc71
        )
        embed.add_field(name="👑 Капитан:", value=self.captain_name.value, inline=True)
        embed.add_field(name="🎮 Игра:", value=game.upper(), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ===== ФУНКЦИЯ СОЗДАНИЯ ПОЛНОЦЕННОГО КЛОЗА =====
async def create_full_clash(interaction: discord.Interaction, team_name: str, captain_name: str, game_type: str):
    """Создает полноценный клоз с ролями, войсами и панелями"""
    
    # Форматируем название категории по игре и нику капитана
    game_display_names = {
        "dota 2": "Dota 2",
        "cs2": "CS2"
    }
    
    game_display = game_display_names.get(game_type.lower(), game_type.upper())
    category_name = f"🎮 {game_display} | {captain_name}"
    
    # Создаем уникальные роли для клоза
    team_role = await interaction.guild.create_role(
        name=f"👥 {team_name}",
        color=discord.Color.green(),
        hoist=True
    )
    
    opponent_role = await interaction.guild.create_role(
        name=f"⚔️ {team_name}",
        color=discord.Color.red(),
        hoist=True
    )
    
    # Настройки прав доступа
    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False, connect=False),
        team_role: discord.PermissionOverwrite(read_messages=True, connect=True, send_messages=True),
        opponent_role: discord.PermissionOverwrite(read_messages=True, connect=True, send_messages=True),
        interaction.guild.me: discord.PermissionOverwrite(read_messages=True, connect=True, send_messages=True)
    }
    
    # Создаем категорию
    category = await interaction.guild.create_category(
        name=category_name,
        overwrites=overwrites
    )
    
    # Создаем текстовые каналы
    info_channel = await category.create_text_channel(f"📋-{team_name}-инфо")
    chat_channel = await category.create_text_channel(f"💬-{team_name}-чат")
    coordination_channel = await category.create_text_channel(f"🎯-пригласить-игроков")
    
    # Создаем войс-каналы с ограничением на 5 человек
    ally_voice = await category.create_voice_channel(
        name=f"🟢-союзники-{team_name}",
        user_limit=5
    )
    
    enemy_voice = await category.create_voice_channel(
        name=f"🔴-противники-{team_name}",
        user_limit=5
    )
    
    # Добавляем капитана в роль команды
    await interaction.user.add_roles(team_role)
    
    # Отправляем панель приглашения в канал координации
    invite_embed = discord.Embed(
        title=f"🎮 Панель управления клозом {team_name}",
        description="Используйте кнопки ниже для приглашения участников",
        color=0x9b59b6
    )
    invite_embed.add_field(name="🟢 Союзники", value="Ваша команда", inline=True)
    invite_embed.add_field(name="🔴 Противники", value="Команда оппонентов", inline=True)
    invite_embed.add_field(name="🎮 Игра", value=game_display, inline=True)
    
    await coordination_channel.send(embed=invite_embed, view=ClashInviteView(team_role.id, opponent_role.id, team_name))
    
    # Отправляем информационное сообщение с источниками
    sources_embed = discord.Embed(
        title="📚 Полезные источники",
        color=0x3498db
    )
    
    if game_type.lower() == "dota 2":
        sources_embed.description = "**Для Dota 2:**"
        sources_embed.add_field(
            name="📊 Статистика и аналитика",
            value="• [DotaBuff](https://www.dotabuff.com)\n• [Stratz](https://stratz.com)\n• [Dota2ProTracker](https://www.dota2protracker.com)",
            inline=False
        )
    elif game_type.lower() == "cs2":
        sources_embed.description = "**Для CS2:**"
        sources_embed.add_field(
            name="📊 Статистика и аналитика", 
            value="• [HLTV](https://www.hltv.org)\n• [Leetify](https://leetify.com)\n• [ScopeGG](https://scope.gg)",
            inline=False
        )
    
    sources_message = await info_channel.send(embed=sources_embed)
    await sources_message.pin()
    
    # Запускаем таймер удаления через 4 часа
    asyncio.create_task(delete_close_after_delay(category, 4 * 60 * 60))
    
    return category

# ===== ФУНКЦИЯ АВТОУДАЛЕНИЯ КЛОЗОВ ЧЕРЕЗ 4 ЧАСА =====
async def delete_close_after_delay(category, delay_seconds):
    """Удаляет клоз через указанное время"""
    await asyncio.sleep(delay_seconds)
    
    try:
        # Удаляем все роли связанные с клозом
        for role in category.guild.roles:
            if "👥" in role.name or "⚔️" in role.name:
                # Проверяем что роль принадлежит этому клозу
                role_team_name = role.name.split(' ', 1)[1] if ' ' in role.name else role.name
                if role_team_name in category.name:
                    await role.delete()
        
        # Удаляем все каналы в категории
        for channel in category.channels:
            await channel.delete()
        
        # Удаляем саму категорию
        await category.delete()
        
    except discord.NotFound:
        pass  # Категория уже удалена
    except Exception as e:
        print(f"❌ Ошибка удаления клоза: {e}")

# ===== ОСНОВНАЯ ПАНЕЛЬ С КЛОЗАМИ =====
class MainPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label='📝 Регистрация команды', style=discord.ButtonStyle.primary, custom_id='register_btn')
    async def register_team(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RegistrationModal())
    
    @discord.ui.button(label='🎮 Создать полноценный клоз', style=discord.ButtonStyle.success, custom_id='create_full_clash_btn')
    async def create_full_clash(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)
        
        # Проверяем регистрацию
        if user_id not in registered_teams:
            await interaction.response.send_message(
                "❌ Сначала зарегистрируйте команду через кнопку '📝 Регистрация команды'!", 
                ephemeral=True
            )
            return
        
        team_data = registered_teams[user_id]
        
        # Проверяем лимит клозов (2 на пользователя)
        user_closes = sum(1 for category in interaction.guild.categories 
                         if f"🎮 {interaction.user.display_name}" in category.name)
        if user_closes >= 2:
            await interaction.response.send_message(
                "❌ У вас уже есть 2 активных клоза! Дождитесь их удаления.", 
                ephemeral=True
            )
            return
        
        # Создаем полноценный клоз
        category = await create_full_clash(
            interaction, 
            team_data['team_name'],
            team_data['captain'], 
            team_data['game']
        )
        
        await interaction.response.send_message(
            f"✅ Полноценный клоз создан! {category.mention}\n"
            f"• 🟢 Войс для союзников (5 слотов)\n" 
            f"• 🔴 Войс для противников (5 слотов)\n"
            f"• 📚 Полезные источники\n"
            f"• 👥 Панель приглашения\n"
            f"• ⏰ Удалится через 4 часа", 
            ephemeral=True
        )
    
    @discord.ui.button(label='📊 Список команд', style=discord.ButtonStyle.secondary, custom_id='teams_list_btn')
    async def show_teams(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not registered_teams:
            embed = discord.Embed(title="📊 Список команд", description="Пока никто не зарегистрировался", color=0xf39c12)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        teams_list = ""
        for user_id, team_data in registered_teams.items():
            user = await bot.fetch_user(int(user_id))
            username = user.name if user else "Неизвестный"
            teams_list += f"• **{team_data['team_name']}** ({team_data['game'].upper()}) - {username}\n"
        
        embed = discord.Embed(title="📊 Зарегистрированные команды", description=teams_list, color=0x2ecc71)
        embed.add_field(name="📈 Статистика:", value=f"Всего команд: **{len(registered_teams)}**", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ===== ПАНЕЛЬ МОДЕРАЦИИ =====
class AdminPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label='👁️ Просмотреть заявки', style=discord.ButtonStyle.primary, custom_id='view_apps_btn')
    async def view_applications(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not registered_teams:
            await interaction.response.send_message("❌ Нет зарегистрированных команд.", ephemeral=True)
            return
        
        embed = discord.Embed(title="📋 Все зарегистрированные команды", color=0x3498db)
        for user_id, team_data in registered_teams.items():
            user = await bot.fetch_user(int(user_id))
            username = user.name if user else "Неизвестный"
            embed.add_field(
                name=f"🏷️ {team_data['team_name']} ({team_data['game'].upper()})", 
                value=f"Капитан: {username}", 
                inline=False
            )
        
        embed.set_footer(text=f"Всего команд: {len(registered_teams)}")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(label='📤 Экспорт в файл', style=discord.ButtonStyle.secondary, custom_id='export_btn')
    async def export_teams(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not registered_teams:
            await interaction.response.send_message("❌ Нет данных для экспорта.", ephemeral=True)
            return
        
        filename = f"teams_export_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            for user_id, team_data in registered_teams.items():
                user = await bot.fetch_user(int(user_id))
                username = user.name if user else "Неизвестный"
                f.write(f"Команда: {team_data['team_name']} | Игра: {team_data['game']} | Капитан: {username}\n")
        
        await interaction.response.send_message(file=discord.File(filename), ephemeral=True)
        os.remove(filename)
    
    @discord.ui.button(label='🗑️ Очистить заявки', style=discord.ButtonStyle.danger, custom_id='clear_btn')
    async def clear_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not registered_teams:
            await interaction.response.send_message("❌ Нет данных для очистки.", ephemeral=True)
            return
        
        confirm_view = ConfirmClearView()
        await interaction.response.send_message("⚠️ Удалить ВСЕ зарегистрированные команды?", view=confirm_view, ephemeral=True)

class ConfirmClearView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)
    
    @discord.ui.button(label='✅ Да', style=discord.ButtonStyle.danger)
    async def confirm_clear(self, interaction: discord.Interaction, button: discord.ui.Button):
        global registered_teams
        count = len(registered_teams)
        registered_teams = {}
        save_teams()
        await interaction.response.send_message(f"✅ Удалено {count} команд!", ephemeral=True)
    
    @discord.ui.button(label='❌ Нет', style=discord.ButtonStyle.secondary)
    async def cancel_clear(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("❌ Очистка отменена.", ephemeral=True)

# ===== ОБРАБОТЧИКИ СОБЫТИЙ =====
@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user} запущен!')
    print(f'✅ Загружено команд: {len(registered_teams)}')

@bot.event
async def on_message(message):
    violation = await mod_system.analyze_message(message)
    if violation:
        await message.delete()
        await mod_system.apply_punishment(message.author, violation, message.channel)

# ===== КОМАНДЫ =====
@bot.tree.command(name="panel", description="📊 Установить панель для игроков")
async def setup_panel(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Нет прав!", ephemeral=True)
        return
    
    embed = discord.Embed(title="🎮 Панель управления командами", description="Все инструменты для организации игрового процесса", color=0x9b59b6)
    embed.add_field(name="📝 Регистрация команды", value="Зарегистрируйте команду для доступа ко всем функциям", inline=False)
    embed.add_field(name="🎮 Создать полноценный клоз", value="Полноценная игровая комната с ролями, войсами и панелями", inline=False)
    embed.add_field(name="📊 Список команд", value="Посмотреть все зарегистрированные команды", inline=False)
    
    await interaction.channel.send(embed=embed, view=MainPanelView())
    await interaction.response.send_message("✅ Панель установлена!", ephemeral=True)

@bot.tree.command(name="modpanel", description="🛠️ Панель модерации")
@app_commands.checks.has_permissions(administrator=True)
async def admin_panel(interaction: discord.Interaction):
    embed = discord.Embed(title="🛠️ Панель модерации", description="Инструменты для управления заявками", color=0xe74c3c)
    embed.add_field(name="👁️ Просмотреть заявки", value="Список всех зарегистрированных команд", inline=False)
    embed.add_field(name="📤 Экспорт в файл", value="Скачать список команд", inline=False)
    embed.add_field(name="🗑️ Очистить заявки", value="Полная очистка базы", inline=False)
    
    await interaction.channel.send(embed=embed, view=AdminPanelView())
    await interaction.response.send_message("✅ Панель модерации установлена!", ephemeral=True)

@bot.tree.command(name="warn", description="Выдать предупреждение")
@app_commands.checks.has_permissions(manage_messages=True)
async def warn_user(interaction: discord.Interaction, пользователь: discord.Member, причина: str):
    await mod_system.apply_punishment(пользователь, "LEVEL1", interaction.channel, причина)
    await interaction.response.send_message(f"✅ {пользователь.mention} получил предупреждение", ephemeral=True)

@bot.tree.command(name="clear_warns", description="Сбросить предупреждения")
@app_commands.checks.has_permissions(administrator=True)
async def clear_warnings(interaction: discord.Interaction, пользователь: discord.Member):
    user_id = пользователь.id
    mod_system.warning_timestamps[user_id] = []
    embed = discord.Embed(title="✅ Предупреждения сброшены", color=0x2ecc71)
    embed.add_field(name="Участник", value=пользователь.mention, inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ===== МОНИТОРИНГ =====
app = Flask(__name__)

@app.route('/')
def home():
    return "ALIVE", 200

def run_server():
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

flask_thread = threading.Thread(target=run_server)
flask_thread.daemon = True
flask_thread.start()
print("✅ Мониторинг запущен на порту 5000")

# ===== ЗАПУСК =====
bot.run(os.getenv('TOKEN'))

